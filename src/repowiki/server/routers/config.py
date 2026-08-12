"""prompt-template management endpoints.

Exposes the 5 analysis/chat prompt templates so they can be viewed and edited
from the web UI (Settings -> Prompt Templates). Edits are persisted to
~/.repowiki/prompts.json and take effect on the next scan/chat.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from repowiki.llm.prompts import (
    DEFAULT_PROMPTS,
    PROMPT_KEYS,
    get_effective_prompts,
    reset_custom_prompts,
    save_custom_prompts,
)

router = APIRouter()


class PromptUpdate(BaseModel):
    prompts: dict[str, dict[str, str]]


@router.get("/prompts")
async def get_prompts():
    """return the current effective prompts plus the defaults (for 'reset')."""
    return {
        "current": get_effective_prompts(),
        "defaults": DEFAULT_PROMPTS,
        "keys": list(PROMPT_KEYS),
    }


@router.put("/prompts")
async def put_prompts(update: PromptUpdate):
    """persist user-provided prompt overrides."""
    save_custom_prompts(update.prompts)
    return {"saved": True, "current": get_effective_prompts()}


@router.post("/prompts/reset")
async def reset_prompts():
    """wipe overrides, restoring all defaults."""
    removed = reset_custom_prompts()
    return {"reset": True, "removed_file": removed, "current": get_effective_prompts()}
