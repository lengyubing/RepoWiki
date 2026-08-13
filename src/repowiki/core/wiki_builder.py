"""assemble wiki pages from analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field

from repowiki.core.graph import DependencyGraph
from repowiki.core.models import ProjectContext, WikiData


@dataclass
class WikiPage:
    id: str
    title: str
    content: str
    parent_id: str = ""
    order: int = 0


@dataclass
class SidebarItem:
    title: str
    page_id: str
    children: list[SidebarItem] = field(default_factory=list)


@dataclass
class Wiki:
    pages: list[WikiPage] = field(default_factory=list)
    sidebar: list[SidebarItem] = field(default_factory=list)
    project_name: str = ""

    def get_page(self, page_id: str) -> WikiPage | None:
        for p in self.pages:
            if p.id == page_id:
                return p
        return None


class WikiBuilder:
    """constructs a Wiki from analysis results."""

    def build(
        self,
        project: ProjectContext,
        wiki_data: WikiData,
        graph: DependencyGraph,
    ) -> Wiki:
        pages: list[WikiPage] = []
        sidebar: list[SidebarItem] = []

        # 1. index / overview page
        overview = wiki_data.overview
        overview_md = self._build_overview_page(overview, project)
        pages.append(WikiPage(id="index", title="系统全览", content=overview_md, order=0))
        sidebar.append(SidebarItem(title="系统全览", page_id="index"))

        # 2. business process page
        bp = wiki_data.business_process
        if bp.processes:
            bp_md = self._build_business_process_page(bp)
            pages.append(WikiPage(id="business-process", title="业务流程", content=bp_md, order=1))
            sidebar.append(SidebarItem(title="业务流程", page_id="business-process"))

        # 3. architecture page
        arch = wiki_data.architecture
        if arch.architecture_type:
            arch_md = self._build_architecture_page(arch)
            pages.append(WikiPage(id="architecture", title="系统架构", content=arch_md, order=2))
            sidebar.append(SidebarItem(title="系统架构", page_id="architecture"))

        # 4. data flow page
        df = wiki_data.data_flow
        if df.summary or df.mermaid:
            df_md = self._build_data_flow_page(df)
            pages.append(WikiPage(id="data-flow", title="数据流图", content=df_md, order=3))
            sidebar.append(SidebarItem(title="数据流图", page_id="data-flow"))

        # 5. reading guide
        guide = wiki_data.reading_guide
        if guide.steps:
            guide_md = self._build_reading_guide_page(guide)
            pages.append(WikiPage(id="reading-guide", title="阅读指南", content=guide_md, order=10))
            sidebar.append(SidebarItem(title="阅读指南", page_id="reading-guide"))

        # 6. dependency graph
        mermaid = graph.to_mermaid()
        if mermaid:
            dep_md = self._build_dependency_page(graph, mermaid)
            pages.append(WikiPage(id="dependencies", title="依赖关系", content=dep_md, order=11))
            sidebar.append(SidebarItem(title="依赖关系", page_id="dependencies"))

        return Wiki(pages=pages, sidebar=sidebar, project_name=project.name)

    def add_page(self, wiki: Wiki, page_id: str, title: str, content: str) -> Wiki:
        """add a dynamically generated page (e.g. deep-dive) to an existing wiki.

        If the page_id already exists, it's updated in place.
        """
        existing = wiki.get_page(page_id)
        if existing:
            existing.title = title
            existing.content = content
        else:
            wiki.pages.append(WikiPage(id=page_id, title=title, content=content, order=20))
            # add to sidebar under a "深度分析" group
            dd_group = next((s for s in wiki.sidebar if s.page_id == "__deep_dives__"), None)
            if dd_group is None:
                dd_group = SidebarItem(title="深度分析", page_id="__deep_dives__", children=[])
                wiki.sidebar.insert(-1 if wiki.sidebar else 0, dd_group)
            dd_group.children.append(SidebarItem(title=title, page_id=page_id))
        return wiki

    def _build_overview_page(self, overview, project) -> str:
        lines = [f"# {overview.name or project.name}\n"]
        if overview.one_liner:
            lines.append(f"> {overview.one_liner}\n")
        if overview.description:
            lines.append(f"{overview.description}\n")

        if overview.tech_stack:
            lines.append("## Tech Stack\n")
            for t in overview.tech_stack:
                ver = f" {t.version}" if t.version else ""
                cat = f" ({t.category})" if t.category else ""
                lines.append(f"- **{t.name}**{ver}{cat}")
            lines.append("")

        if overview.key_features:
            lines.append("## Key Features\n")
            for feat in overview.key_features:
                lines.append(f"- {feat}")
            lines.append("")

        if overview.business_cases:
            lines.append("## Business Cases\n")
            for bc in overview.business_cases:
                lines.append(f"- {bc}")
            lines.append("")

        if overview.formulas:
            lines.append("## Key Formulas\n")
            for fm in overview.formulas:
                lines.append(f"### {fm.name}\n" if fm.name else "")
                if fm.expression:
                    lines.append(f"```\n{fm.expression}\n```\n")
                if fm.explanation:
                    lines.append(f"{fm.explanation}\n")
            lines.append("")

        if overview.setup_instructions:
            lines.append("## Getting Started\n")
            for i, step in enumerate(overview.setup_instructions, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        return "\n".join(lines)

    def _build_architecture_page(self, arch) -> str:
        lines = ["# Architecture\n"]
        if arch.architecture_type:
            lines.append(f"**Type:** {arch.architecture_type}\n")
        if arch.description:
            lines.append(f"{arch.description}\n")

        if arch.mermaid_component:
            lines.append("## Component Diagram\n")
            lines.append(f"```mermaid\n{arch.mermaid_component}\n```\n")

        if arch.components:
            lines.append("## Components\n")
            for c in arch.components:
                lines.append(f"### {c.name}\n")
                if c.purpose:
                    lines.append(f"{c.purpose}\n")
                if c.files:
                    lines.append("Files: " + ", ".join(f"`{f}`" for f in c.files) + "\n")

        if arch.mermaid_sequence:
            lines.append("## Sequence Diagram\n")
            lines.append(f"```mermaid\n{arch.mermaid_sequence}\n```\n")

        if arch.data_flow:
            lines.append("## Data Flow\n")
            lines.append(f"{arch.data_flow}\n")

        if arch.service_dependencies:
            lines.append("## Service Dependencies\n")
            lines.append("External systems this project connects to at runtime:\n")
            for d in arch.service_dependencies:
                cat = f" ({d.category})" if d.category else ""
                purpose = f" — {d.purpose}" if d.purpose else ""
                lines.append(f"- **{d.name}**{cat}{purpose}")
            lines.append("")

        if arch.framework_dependencies:
            lines.append("## Framework Dependencies\n")
            lines.append("Libraries and frameworks the code is built on:\n")
            for d in arch.framework_dependencies:
                cat = f" ({d.category})" if d.category else ""
                purpose = f" — {d.purpose}" if d.purpose else ""
                lines.append(f"- **{d.name}**{cat}{purpose}")
            lines.append("")

        return "\n".join(lines)

    def _build_module_page(self, mod) -> str:
        lines = [f"# {mod.name}\n"]
        if mod.purpose:
            lines.append(f"> {mod.purpose}\n")
        if mod.description:
            lines.append(f"{mod.description}\n")

        if mod.business_logic:
            lines.append("## Business Logic & Data Flow\n")
            lines.append(f"{mod.business_logic}\n")

        if mod.files:
            lines.append("## Files\n")
            for f in mod.files:
                lines.append(f"### `{f.path}`\n")
                if f.purpose:
                    lines.append(f"{f.purpose}\n")
                if f.key_symbols:
                    for s in f.key_symbols:
                        desc = f" - {s.description}" if s.description else ""
                        lines.append(f"- `{s.name}` ({s.kind}){desc}")
                    lines.append("")

        if mod.key_concepts:
            lines.append("## Key Concepts\n")
            for c in mod.key_concepts:
                lines.append(f"- **{c.name}**: {c.explanation}")
            lines.append("")

        if mod.relationships:
            lines.append("## Internal Relationships\n")
            for r in mod.relationships:
                lines.append(f"- `{r.source}` → `{r.target}`: {r.description}")
            lines.append("")

        if mod.potential_issues:
            lines.append("## Potential Issues\n")
            for issue in mod.potential_issues:
                lines.append(f"- ⚠️ {issue}")
            lines.append("")

        if mod.optimization_points:
            lines.append("## Optimization Points\n")
            for opt in mod.optimization_points:
                lines.append(f"- 💡 {opt}")
            lines.append("")

        return "\n".join(lines)

    def _build_reading_guide_page(self, guide) -> str:
        lines = ["# Reading Guide\n"]
        if guide.introduction:
            lines.append(f"{guide.introduction}\n")

        for step in guide.steps:
            time_est = f" (~{step.time_estimate})" if step.time_estimate else ""
            lines.append(f"## Step {step.order}: {step.title}{time_est}\n")
            if step.files:
                lines.append("**Files:** " + ", ".join(f"`{f}`" for f in step.files) + "\n")
            if step.explanation:
                lines.append(f"{step.explanation}\n")

        if guide.tips:
            lines.append("## Tips\n")
            for tip in guide.tips:
                lines.append(f"- {tip}")
            lines.append("")

        return "\n".join(lines)

    def _build_business_process_page(self, bp) -> str:
        lines = ["# 业务流程\n"]
        if bp.introduction:
            lines.append(f"{bp.introduction}\n")

        for proc in bp.processes:
            lines.append(f"## {proc.order}. {proc.title}\n")
            if proc.trigger:
                lines.append(f"**触发条件：** {proc.trigger}\n")
            if proc.flow:
                lines.append(f"**处理流程：**\n\n{proc.flow}\n")
            if proc.outcome:
                lines.append(f"**结果：** {proc.outcome}\n")
            if proc.key_methods:
                lines.append("**关键方法：** " + ", ".join(f"`{m}`" for m in proc.key_methods) + "\n")

        return "\n".join(lines)

    def _build_data_flow_page(self, df) -> str:
        lines = ["# 数据流图\n"]
        if df.summary:
            lines.append(f"{df.summary}\n")

        if df.mermaid:
            lines.append("## 数据流图\n")
            lines.append(f"```mermaid\n{df.mermaid}\n```\n")

        if df.entities:
            lines.append("## 核心数据实体\n")
            for e in df.entities:
                lines.append(f"- {e}")
            lines.append("")

        if df.transformations:
            lines.append("## 数据转换步骤\n")
            for t in df.transformations:
                lines.append(f"- {t}")
            lines.append("")

        return "\n".join(lines)

    def _build_dependency_page(self, graph: DependencyGraph, mermaid: str) -> str:
        lines = ["# Module Dependencies\n"]
        lines.append("```mermaid\n" + mermaid + "\n```\n")

        # core files
        core = graph.get_core_files(10)
        if core:
            lines.append("## Core Files (by PageRank)\n")
            for i, path in enumerate(core, 1):
                lines.append(f"{i}. `{path}`")
            lines.append("")

        # entry points
        entries = graph.get_entry_points()
        if entries:
            lines.append("## Likely Entry Points\n")
            for e in entries[:10]:
                lines.append(f"- `{e}`")
            lines.append("")

        # circular dependencies (an architectural smell worth surfacing)
        cycles = graph.find_circular_dependencies()
        if cycles:
            lines.append("## Circular Dependencies\n")
            lines.append(
                "These groups of files import each other in a cycle, so you can't "
                "fully understand one without the others; consider breaking the loop "
                "to reduce coupling.\n"
            )
            for cycle in cycles:
                files = ", ".join(f"`{p}`" for p in cycle)
                lines.append(f"- {files}")
            lines.append("")

        # isolated files (likely dead code worth surfacing)
        isolated = graph.find_isolated_files()
        if isolated:
            lines.append("## Isolated Files\n")
            lines.append(
                "These files import nothing in the project and are imported by "
                "nothing -- likely dead code, stray scripts, or modules that were "
                "never wired in.\n"
            )
            for f in isolated[:15]:
                lines.append(f"- `{f}`")
            lines.append("")

        return "\n".join(lines)
