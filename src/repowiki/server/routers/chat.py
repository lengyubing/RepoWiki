"""Q&A chat endpoint with RAG."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from repowiki.config import Config, resolve_model
from repowiki.server.app import get_projects
from repowiki.server.models import ChatRequest

router = APIRouter()


def _build_wiki_context(wiki, question: str) -> str:
    """extract relevant business analysis from the generated wiki to augment chat.

    Finds modules whose name/description/business_logic overlap with the question
    keywords, and returns their analysis as a context block. This lets the chat
    answer business-flow questions that RAG code chunks alone can't cover.
    """
    if not wiki:
        return ""

    # tokenize the question for matching (reuse the same logic as RAG)
    from repowiki.core.rag import _tokenize
    q_tokens = set(t.lower() for t in _tokenize(question) if len(t) > 1)
    if not q_tokens:
        return ""

    blocks = []
    for mod in getattr(wiki, "modules", []):
        # score this module against the question
        mod_text = " ".join([
            mod.name or "", mod.purpose or "", mod.description or "",
            mod.business_logic or "",
            " ".join(c.name + " " + c.explanation for c in mod.key_concepts),
        ]).lower()
        mod_tokens = set(t.lower() for t in _tokenize(mod_text) if len(t) > 1)
        overlap = q_tokens & mod_tokens
        # require at least 2 keyword overlaps to include this module
        if len(overlap) < 2:
            continue

        parts = [f"### Wiki Analysis: {mod.name} module"]
        if mod.purpose:
            parts.append(f"**Purpose:** {mod.purpose}")
        if mod.description:
            parts.append(f"**Description:** {mod.description}")
        if mod.business_logic:
            parts.append(f"**Business Logic:**\n{mod.business_logic}")
        if mod.key_concepts:
            concepts = "\n".join(f"- **{c.name}**: {c.explanation}" for c in mod.key_concepts)
            parts.append(f"**Key Concepts:**\n{concepts}")
        blocks.append("\n".join(parts))

    if not blocks:
        return ""

    header = (
        "## Wiki Analysis (previously generated business analysis — use this "
        "for business logic and data flow questions):\n\n"
    )
    return header + "\n\n---\n\n".join(blocks)


@router.post("/project/{project_id}/chat")
async def chat(project_id: str, req: ChatRequest, x_api_key: str | None = Header(None)):
    """SSE streaming chat response with RAG retrieval."""
    projects = get_projects()
    proj = projects.get(project_id)
    if not proj or not proj.get("project"):
        return {"error": "Project not ready"}

    project = proj["project"]

    # build RAG index if not cached
    if "rag" not in proj:
        from repowiki.core.rag import SimpleRAG
        rag = SimpleRAG()
        rag.index(project)
        proj["rag"] = rag
    else:
        rag = proj["rag"]

    # retrieve relevant chunks
    chunks = rag.retrieve(req.question, top_k=5)
    context_parts = []
    references = []
    for chunk in chunks:
        context_parts.append(
            f"### {chunk.file_path} (lines {chunk.line_start}-{chunk.line_end})\n"
            f"```\n{chunk.content}\n```"
        )
        references.append({
            "path": chunk.file_path,
            "line_start": chunk.line_start,
            "line_end": chunk.line_end,
            "snippet": chunk.content[:200],
        })

    context_text = "\n\n".join(context_parts)

    # also pull in relevant wiki analysis (business logic, module descriptions,
    # key concepts) as high-level context. RAG code chunks alone miss cross-file
    # business flows; the wiki's analysis fills that gap.
    wiki_context = _build_wiki_context(proj.get("wiki"), req.question)
    if wiki_context:
        context_text = wiki_context + "\n\n" + context_text

    # Resolve LLM config. Priority (highest first):
    #   1. request body (what the user just picked in Settings)
    #   2. scan-time snapshot stored on the project entry
    #   3. Config.load() defaults (config file / env vars)
    saved = proj.get("llm_config") or {}
    cfg = Config.load()
    # base layer: scan-time snapshot
    if saved.get("model"):
        cfg.model = saved["model"]
    if saved.get("api_base"):
        cfg.api_base = saved["api_base"]
    if saved.get("language"):
        cfg.language = saved["language"]
    # top layer: request overrides (current Settings selection wins)
    if req.model:
        cfg.model = resolve_model(req.model)
    if req.api_base:
        cfg.api_base = req.api_base
    # api_key: header override > saved > config file / env
    if x_api_key:
        cfg.api_key = x_api_key
    elif saved.get("api_key"):
        cfg.api_key = saved["api_key"]

    if not cfg.api_key:
        return {"error": "No API key configured"}

    from repowiki.llm.client import LLMClient
    from repowiki.llm.prompts import build_chat_prompt

    llm = LLMClient(model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base)
    messages = build_chat_prompt(req.question, context_text, cfg.language)

    async def event_stream():
        # send references first
        yield f"data: {json.dumps({'references': references})}\n\n"

        # stream the answer; detect LLM errors so we can surface them as a
        # proper error event instead of passing the error string off as content.
        had_content = False
        async for chunk in llm.stream(messages):
            if chunk.startswith("[LLM Error:"):
                yield f"data: {json.dumps({'error': chunk, 'model': cfg.model, 'api_base': cfg.api_base or '(provider default)'})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            had_content = True
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        if not had_content:
            yield f"data: {json.dumps({'error': 'No response from model. Check your API key and Base URL in Settings.', 'model': cfg.model, 'api_base': cfg.api_base or '(provider default)'})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
