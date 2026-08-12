"""scan and project management endpoints."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Header
from fastapi.responses import StreamingResponse

from repowiki.config import Config, resolve_model
from repowiki.server.app import get_cache, get_projects
from repowiki.server.models import ProjectInfo, ScanRequest

router = APIRouter()


@router.post("/scan", response_model=ProjectInfo)
async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks,
                     x_api_key: str | None = Header(None)):
    project_id = str(uuid.uuid4())[:8]
    # remember the original input (local path or URL) for the project list
    source = (req.path or req.url or "").strip()
    info = ProjectInfo(id=project_id, name="", status="pending", source=source, created_at=time.time())
    projects = get_projects()
    projects[project_id] = {"info": info, "wiki": None, "project": None, "progress": []}

    background_tasks.add_task(_run_scan, project_id, req, x_api_key)
    return info


@router.get("/projects")
async def list_projects():
    """list all known projects (in-memory + persisted), newest first."""
    projects = get_projects()
    seen: set[str] = set()
    items: list[dict] = []
    # in-memory entries first (most recent activity)
    for project_id, proj in projects.items():
        seen.add(project_id)
        info: ProjectInfo = proj["info"]
        items.append(info.model_dump())
    # then any persisted-only entries (recovered at startup, not yet re-scanned)
    cache = get_cache()
    try:
        for project_id, data, _created_at in await cache.list_projects():
            if project_id in seen:
                continue
            info_data = data.get("info") if isinstance(data, dict) else None
            if isinstance(info_data, dict):
                items.append(info_data)
    except Exception:
        pass
    # sort by created_at descending
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return {"projects": items}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """remove a project from memory and from persisted storage."""
    projects = get_projects()
    removed_mem = projects.pop(project_id, None) is not None
    cache = get_cache()
    try:
        await cache.delete_project(project_id)
    except Exception:
        pass
    return {"deleted": removed_mem, "id": project_id}


@router.post("/project/{project_id}/reanalyze")
async def reanalyze_project(project_id: str, background_tasks: BackgroundTasks):
    """re-run the LLM analysis for an already-ingested project, ignoring cache.

    The project must have been scanned before (its ingested files are reused so
    there's no re-clone / re-scan of the directory). Useful after editing prompt
    templates or switching models.
    """
    projects = get_projects()
    proj = projects.get(project_id)
    if not proj:
        return {"error": "Project not found"}
    if not proj.get("project"):
        return {"error": "Project has no ingested files. Re-scan it from the home page first."}

    proj["info"].status = "scanning"
    proj["progress"] = []
    background_tasks.add_task(_run_reanalyze, project_id)
    return proj["info"]


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    projects = get_projects()
    if project_id not in projects:
        return {"error": "Project not found"}
    return projects[project_id]["info"]


@router.get("/project/{project_id}/status")
async def stream_status(project_id: str):
    """SSE endpoint for scan progress updates."""
    async def event_stream():
        projects = get_projects()
        if project_id not in projects:
            yield f"data: {json.dumps({'error': 'not found'})}\n\n"
            return

        seen = 0
        while True:
            proj = projects.get(project_id)
            if not proj:
                break

            progress = proj.get("progress", [])
            while seen < len(progress):
                yield f"data: {json.dumps({'step': progress[seen]})}\n\n"
                seen += 1

            if proj["info"].status in ("done", "error"):
                yield f"data: {json.dumps({'status': proj['info'].status})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _run_scan(project_id: str, req: ScanRequest, user_api_key: str | None):
    """background task that runs the full scan + analysis pipeline."""
    projects = get_projects()
    proj = projects[project_id]
    proj["info"].status = "scanning"

    try:
        cfg = Config.load()
        if req.language:
            cfg.language = req.language
        if req.model:
            cfg.model = resolve_model(req.model)
        if user_api_key:
            cfg.api_key = user_api_key
        elif req.api_key:
            cfg.api_key = req.api_key
        if req.api_base:
            cfg.api_base = req.api_base

        # persist the resolved LLM config on the project entry so the chat
        # endpoint reuses the same model/api_key/api_base the user picked at
        # scan time, instead of falling back to defaults.
        proj["llm_config"] = {
            "model": cfg.model,
            "api_key": cfg.api_key,
            "api_base": cfg.api_base,
            "language": cfg.language,
        }

        def progress(msg: str):
            proj["progress"].append(msg)

        # ingest
        progress("Ingesting project...")

        # resolve the target: prefer an explicit local path, then a URL, then a
        # value typed into the URL box that is actually a local path. This keeps
        # the web UI's single-input behavior consistent with the CLI.
        from pathlib import Path

        from repowiki.ingest.github import parse_git_url

        local_path: str | None = None
        remote_url: str | None = None

        if req.path:
            local_path = req.path
        elif req.url:
            # a real URL (http...) or a recognized git host string -> remote
            if req.url.startswith("http") or parse_git_url(req.url) is not None:
                remote_url = req.url
            elif Path(req.url).exists():
                # user typed a local path into the URL box
                local_path = req.url
            else:
                remote_url = req.url  # let ingest_github raise a clear error

        if local_path:
            from repowiki.ingest.local import ingest_local
            project = ingest_local(local_path, max_file_size=cfg.max_file_size, max_files=cfg.max_files)
        elif remote_url:
            from repowiki.ingest.github import ingest_github
            project = ingest_github(remote_url, max_file_size=cfg.max_file_size, max_files=cfg.max_files)
        else:
            raise ValueError("Either path or url must be provided")

        proj["project"] = project
        proj["info"].name = project.name
        proj["info"].total_files = len(project.files)
        proj["info"].total_lines = project.total_lines

        # check if we have an API key
        if not cfg.api_key:
            proj["info"].status = "error"
            proj["info"].error = "No API key configured"
            await _persist_project(project_id)
            return

        # analyze
        from repowiki.core.analyzer import Analyzer
        from repowiki.core.graph import DependencyGraph
        from repowiki.core.wiki_builder import WikiBuilder
        from repowiki.llm.client import LLMClient

        cache = get_cache()
        llm = LLMClient(model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base)
        analyzer = Analyzer(llm=llm, cache=cache, language=cfg.language, concurrency=cfg.concurrency)

        wiki_data = await analyzer.analyze(project, on_progress=progress)

        graph = DependencyGraph.build_from_project(project)
        builder = WikiBuilder()
        wiki = builder.build(project, wiki_data, graph)

        proj["wiki"] = wiki
        proj["info"].status = "done"
        progress("Done!")
        await _persist_project(project_id)

    except Exception as e:
        proj["info"].status = "error"
        proj["info"].error = str(e)
        proj["progress"].append(f"Error: {e}")
        await _persist_project(project_id)


async def _persist_project(project_id: str) -> None:
    """save project metadata to SQLite so it survives restarts."""
    projects = get_projects()
    proj = projects.get(project_id)
    if not proj:
        return
    info: ProjectInfo = proj["info"]
    file_tree = ""
    if proj.get("project") is not None:
        file_tree = proj["project"].file_tree or ""
    try:
        cache = get_cache()
        await cache.save_project(project_id, {"info": info.model_dump(), "file_tree": file_tree})
    except Exception:
        pass


async def _run_reanalyze(project_id: str) -> None:
    """re-run the analysis pipeline for an existing project, ignoring LLM cache."""
    projects = get_projects()
    proj = projects.get(project_id)
    if not proj or not proj.get("project"):
        return

    info: ProjectInfo = proj["info"]
    info.status = "scanning"
    info.error = ""
    saved = proj.get("llm_config") or {}

    def progress(msg: str):
        proj["progress"].append(msg)

    try:
        from repowiki.core.analyzer import Analyzer
        from repowiki.core.graph import DependencyGraph
        from repowiki.core.wiki_builder import WikiBuilder
        from repowiki.llm.client import LLMClient

        project = proj["project"]
        cfg = Config.load()
        if saved.get("model"):
            cfg.model = saved["model"]
        if saved.get("api_base"):
            cfg.api_base = saved["api_base"]
        if saved.get("language"):
            cfg.language = saved["language"]
        if saved.get("api_key"):
            cfg.api_key = saved["api_key"]

        if not cfg.api_key:
            info.status = "error"
            info.error = "No API key configured"
            await _persist_project(project_id)
            return

        cache = get_cache()
        llm = LLMClient(model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base)
        analyzer = Analyzer(
            llm=llm, cache=cache, language=cfg.language,
            concurrency=cfg.concurrency, force_refresh=True,
        )

        progress("Re-analyzing (ignoring cache)...")
        wiki_data = await analyzer.analyze(project, on_progress=progress)

        graph = DependencyGraph.build_from_project(project)
        builder = WikiBuilder()
        wiki = builder.build(project, wiki_data, graph)

        proj["wiki"] = wiki
        info.status = "done"
        progress("Done!")
        await _persist_project(project_id)

    except Exception as e:
        info.status = "error"
        info.error = str(e)
        proj["progress"].append(f"Error: {e}")
        await _persist_project(project_id)
