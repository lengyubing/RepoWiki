"""orchestrates the multi-step LLM analysis pipeline."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from repowiki.core.cache import Cache, content_hash
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    BusinessProcess,
    DataFlowDetail,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    WikiData,
)
from repowiki.llm.client import LLMClient
from repowiki.llm.prompts import (
    build_architecture_prompt,
    build_business_process_prompt,
    build_data_flow_prompt,
    build_overview_prompt,
    build_reading_guide_prompt,
    extract_json,
)

logger = logging.getLogger(__name__)


class Analyzer:
    """runs the full wiki generation pipeline."""

    def __init__(
        self,
        llm: LLMClient,
        cache: Cache,
        language: str = "en",
        concurrency: int = 5,
        force_refresh: bool = False,
    ):
        self.llm = llm
        self.cache = cache
        self.language = language
        self.force_refresh = force_refresh
        self._sem = asyncio.Semaphore(concurrency)

    async def _cache_get(self, key: str) -> dict | list | None:
        """cache read that respects force_refresh (skips cache when re-analyzing)."""
        if self.force_refresh:
            return None
        return await self.cache.get(key)

    async def analyze(
        self,
        project: ProjectContext,
        on_progress: Callable[[str], None] | None = None,
    ) -> WikiData:
        """run the full analysis pipeline and return WikiData."""

        def progress(msg: str):
            if on_progress:
                on_progress(msg)

        # 1. prepare context
        progress("Preparing file context...")
        key_files_text = self._build_key_files_context(project)
        tree_hash = content_hash(project.file_tree + key_files_text)

        # 2. generate overview
        progress("Generating project overview...")
        overview = await self._generate_overview(project, key_files_text, tree_hash)

        # 3. generate business process analysis
        progress("Analyzing business processes...")
        business_process = await self._generate_business_process(project, key_files_text, tree_hash)

        # 4. generate architecture diagram
        progress("Detecting architecture...")
        architecture = await self._generate_architecture(project, key_files_text, tree_hash)

        # 5. generate data flow analysis
        progress("Analyzing data flow...")
        data_flow = await self._generate_data_flow(project, key_files_text, tree_hash)

        # 6. generate reading guide
        progress("Creating reading guide...")
        reading_guide = await self._generate_reading_guide(
            project, overview, architecture, tree_hash
        )

        progress("Done!")
        return WikiData(
            overview=overview,
            architecture=architecture,
            business_process=business_process,
            data_flow=data_flow,
            reading_guide=reading_guide,
        )

    def _build_key_files_context(self, project: ProjectContext) -> str:
        """collect config files and entrypoints for the overview prompt."""
        parts = []
        for f in project.files:
            if f.is_config or f.is_entrypoint:
                content = f.content if f.content else f.preview
                # truncate large files
                if len(content) > 4096:
                    content = content[:4096] + "\n... (truncated)"
                parts.append(f"### {f.path}\n```{f.language}\n{content}\n```")
        return "\n\n".join(parts)

    async def _generate_overview(
        self, project: ProjectContext, key_files: str, tree_hash: str
    ) -> ProjectOverview:
        cache_key = f"overview:{self.language}:{tree_hash}"
        cached = await self._cache_get(cache_key)
        if cached:
            try:
                return ProjectOverview(**cached)
            except Exception:
                pass

        messages = build_overview_prompt(
            project.file_tree, key_files, self.language,
            supplementary_docs=project.supplementary_docs,
            custom_instructions=project.custom_instructions,
        )
        raw = await self.llm.complete(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse overview JSON, using defaults")
            return ProjectOverview(name=project.name)

        filtered = {k: v for k, v in data.items() if k in ProjectOverview.model_fields}
        try:
            overview = ProjectOverview(**filtered)
        except Exception:
            overview = ProjectOverview(name=project.name)
        await self.cache.put(cache_key, overview.model_dump())
        return overview

    async def _generate_architecture(
        self, project: ProjectContext, key_files: str, tree_hash: str
    ) -> ArchitectureDiagram:
        cache_key = f"arch:{self.language}:{tree_hash}"
        cached = await self._cache_get(cache_key)
        if cached:
            try:
                return ArchitectureDiagram(**cached)
            except Exception:
                pass

        messages = build_architecture_prompt(
            project.file_tree, key_files, self.language,
            supplementary_docs=project.supplementary_docs,
            custom_instructions=project.custom_instructions,
        )
        raw = await self.llm.complete(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse architecture JSON")
            return ArchitectureDiagram()

        filtered = {k: v for k, v in data.items() if k in ArchitectureDiagram.model_fields}
        try:
            arch = ArchitectureDiagram(**filtered)
        except Exception:
            arch = ArchitectureDiagram()
        await self.cache.put(cache_key, arch.model_dump())
        return arch

    async def _generate_reading_guide(
        self,
        project: ProjectContext,
        overview: ProjectOverview,
        architecture: ArchitectureDiagram,
        tree_hash: str,
    ) -> ReadingGuide:
        # PageRank over the import graph decides which files matter; scan order
        # only fills the tail when the graph is smaller than the display limit.
        ranked = DependencyGraph.build_from_project(project).rank_files()
        by_path = {f.path: f for f in project.files}
        ranked_paths = [path for path, _ in ranked[:20]]
        seen = set(ranked_paths)
        for f in project.files:
            if len(ranked_paths) >= 20:
                break
            if f.path not in seen:
                ranked_paths.append(f.path)
                seen.add(f.path)

        rankings_parts = []
        for i, path in enumerate(ranked_paths, 1):
            f = by_path[path]
            tag = ""
            if f.is_entrypoint:
                tag = " [entrypoint]"
            elif f.is_config:
                tag = " [config]"
            rankings_parts.append(f"{i}. {path}{tag} ({f.lines} lines)")
        rankings = "\n".join(rankings_parts)

        # build summaries from overview + architecture (no longer from per-module docs)
        summary_parts = []
        if overview.one_liner:
            summary_parts.append(f"- **项目概述**: {overview.one_liner}")
        if overview.key_features:
            summary_parts.append(f"- **核心功能**: {', '.join(overview.key_features[:5])}")
        if architecture.components:
            for c in architecture.components[:5]:
                summary_parts.append(f"- **组件 {c.name}**: {c.purpose}")
        module_summaries = "\n".join(summary_parts)

        # key on the actual prompt inputs so an import-only edit that reshuffles
        # the ranking also invalidates the cached guide
        cache_key = f"guide:{self.language}:{tree_hash}:{content_hash(rankings + module_summaries)}"
        cached = await self._cache_get(cache_key)
        if cached:
            try:
                return ReadingGuide(**cached)
            except Exception:
                pass

        messages = build_reading_guide_prompt(
            rankings, module_summaries, self.language,
            custom_instructions=project.custom_instructions,
        )
        raw = await self.llm.complete(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse reading guide JSON")
            return ReadingGuide()

        filtered = {k: v for k, v in data.items() if k in ReadingGuide.model_fields}
        try:
            guide = ReadingGuide(**filtered)
        except Exception:
            guide = ReadingGuide()
        await self.cache.put(cache_key, guide.model_dump())
        return guide

    async def _generate_business_process(
        self, project: ProjectContext, key_files: str, tree_hash: str,
    ) -> BusinessProcess:
        cache_key = f"bizproc:{self.language}:{tree_hash}"
        cached = await self._cache_get(cache_key)
        if cached:
            try:
                return BusinessProcess(**cached)
            except Exception:
                pass

        messages = build_business_process_prompt(
            project.file_tree, key_files, self.language,
            supplementary_docs=project.supplementary_docs,
            custom_instructions=project.custom_instructions,
        )
        raw = await self.llm.complete(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse business process JSON")
            return BusinessProcess()

        filtered = {k: v for k, v in data.items() if k in BusinessProcess.model_fields}
        try:
            bp = BusinessProcess(**filtered)
        except Exception:
            bp = BusinessProcess()
        await self.cache.put(cache_key, bp.model_dump())
        return bp

    async def _generate_data_flow(
        self, project: ProjectContext, key_files: str, tree_hash: str,
    ) -> DataFlowDetail:
        cache_key = f"dataflow:{self.language}:{tree_hash}"
        cached = await self._cache_get(cache_key)
        if cached:
            try:
                return DataFlowDetail(**cached)
            except Exception:
                pass

        messages = build_data_flow_prompt(
            project.file_tree, key_files, self.language,
            supplementary_docs=project.supplementary_docs,
            custom_instructions=project.custom_instructions,
        )
        raw = await self.llm.complete(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse data flow JSON")
            return DataFlowDetail()

        filtered = {k: v for k, v in data.items() if k in DataFlowDetail.model_fields}
        try:
            df = DataFlowDetail(**filtered)
        except Exception:
            df = DataFlowDetail()
        await self.cache.put(cache_key, df.model_dump())
        return df
