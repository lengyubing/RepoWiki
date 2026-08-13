"""FastAPI application for the RepoWiki web interface."""

from __future__ import annotations

from contextlib import asynccontextmanager

from repowiki.core.cache import Cache

# in-memory project store (keyed by project ID)
_projects: dict = {}
_cache: Cache | None = None


def get_cache() -> Cache:
    assert _cache is not None
    return _cache


def get_projects() -> dict:
    return _projects


def create_app():
    """factory function for creating the FastAPI app."""
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise RuntimeError(
            "FastAPI not installed. Run: pip install repowiki[web]"
        )

    @asynccontextmanager
    async def lifespan(app):
        global _cache
        _cache = Cache()
        await _cache.init()
        # restore previously scanned projects from SQLite so they show up on the
        # home page after a restart. Only metadata is restored; the wiki body is
        # rebuilt lazily when the user re-opens the project.
        try:
            from repowiki.server.models import ProjectInfo

            for project_id, data, _created in await _cache.list_projects():
                info_data = data.get("info") if isinstance(data, dict) else None
                if isinstance(info_data, dict):
                    info = ProjectInfo(**{k: v for k, v in info_data.items()
                                          if k in ProjectInfo.model_fields})
                    # a restarted project's wiki is no longer in memory
                    if info.status == "done":
                        info.status = "archived"
                    _projects[project_id] = {"info": info, "wiki": None, "project": None, "progress": []}
        except Exception:
            pass
        yield
        await _cache.close()

    app = FastAPI(
        title="RepoWiki",
        description="Generate wiki documentation for any codebase",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # register routers
    from repowiki.server.routers import chat, config, scan, wiki
    app.include_router(scan.router, prefix="/api")
    app.include_router(wiki.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(config.router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    # serve embedded frontend (if built)
    from pathlib import Path

    from starlette.responses import FileResponse

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        index_html = static_dir / "index.html"

        # SPA fallback: any non-/api GET route that doesn't match a real static
        # file returns index.html so React Router can handle client-side routes.
        # Without this, refreshing /project/xxx returns 404.
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(index_html))

    return app
