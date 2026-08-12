"""prompt templates for repowiki analysis pipeline.

Templates are editable: defaults live in DEFAULT_PROMPTS below, and a user can
override any of them via ~/.repowiki/prompts.json (managed through the web UI's
Settings -> Prompt Templates, or the /api/prompts endpoints). Variable slots use
str.format-style placeholders (e.g. {file_tree}); each builder fills its own.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

_CONFIG_DIR = Path.home() / ".repowiki"
_PROMPTS_FILE = _CONFIG_DIR / "prompts.json"

# The canonical prompt keys. Keep stable; the web UI and API rely on these names.
PROMPT_KEYS = ("overview", "module", "architecture", "reading_guide", "chat")


def _lang_instruction(language: str) -> str:
    lang_map = {
        "en": "Respond in English.",
        "zh": "请用中文回答。",
        "ja": "日本語で回答してください。",
        "ko": "한국어로 답변해주세요.",
    }
    return lang_map.get(language, "Respond in English.")


_JSON_INSTRUCTION = (
    "Output ONLY valid JSON. No markdown fences, no explanation text before or after. "
    "Just the JSON object/array."
)

# Default templates. {lang} is always filled last (after user content), so the
# user-facing templates expose the domain variables ({file_tree}, etc.) while the
# language tag is injected uniformly.
DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "overview": {
        "system": (
            "You are a senior software engineer explaining a project to a new team member. "
            "Be direct, specific, and concrete. "
            "Do NOT use filler phrases like 'leveraging', 'utilizing', 'cutting-edge', "
            "'robust', or 'comprehensive'. Just describe what things do. {lang}"
        ),
        "user": (
            "Here is the file tree and key files of a project:\n\n"
            "## File Tree\n```\n{file_tree}\n```\n\n"
            "## Key Files\n{key_files}\n\n"
            "Generate a project overview as JSON with this structure:\n"
            "{\n"
            '  "name": "project name",\n'
            '  "one_liner": "what this project does in one sentence (max 20 words)",\n'
            '  "description": "2-3 paragraphs explaining the project in plain language",\n'
            '  "tech_stack": [{"name": "Python", "category": "language", "version": "3.10+"}],\n'
            '  "setup_instructions": ["step 1", "step 2"],\n'
            '  "key_features": ["feature 1", "feature 2"]\n'
            "}\n\n"
            "{json_instruction}"
        ),
    },
    "module": {
        "system": (
            "You are a senior engineer documenting your own code. "
            "Be direct and specific. No filler. "
            "Explain what each file does, how files relate to each other, "
            "and what the key functions/classes are. {lang}"
        ),
        "user": (
            "Project: {project_summary}\n\n"
            "Document the '{module_name}' module. Here are its files:\n\n"
            "{files_context}\n\n"
            "Output JSON:\n"
            "{\n"
            '  "name": "{module_name}",\n'
            '  "purpose": "one sentence",\n'
            '  "description": "detailed explanation",\n'
            '  "files": [\n'
            '    {"path": "file.py", "purpose": "what it does", '
            '"key_symbols": [{"name": "func_name", "kind": "function", "description": "..."}]}\n'
            '  ],\n'
            '  "relationships": [{"source": "a.py", "target": "b.py", "description": "a imports b for..."}],\n'
            '  "key_concepts": [{"name": "concept", "explanation": "..."}]\n'
            "}\n\n"
            "{json_instruction}"
        ),
    },
    "architecture": {
        "system": (
            "You are a software architect analyzing a codebase. "
            "Identify the architecture pattern and generate Mermaid diagrams. "
            "Mermaid syntax must be valid. Use simple node names (no special chars). {lang}"
        ),
        "user": (
            "## File Tree\n```\n{file_tree}\n```\n\n"
            "## Key Files\n{key_files}\n\n"
            "Analyze the architecture. Output JSON:\n"
            "{\n"
            '  "architecture_type": "one of: monolith, client-server, microservices, library, cli-tool, framework, plugin-system, pipeline",\n'
            '  "description": "explain the architecture in 2-3 sentences",\n'
            '  "components": [{"name": "...", "purpose": "...", "files": ["..."]}],\n'
            '  "mermaid_component": "graph TD\\n  A[Component] --> B[Component]\\n  ...",\n'
            '  "mermaid_sequence": "sequenceDiagram\\n  participant A\\n  A->>B: request\\n  ...",\n'
            '  "data_flow": "describe the main data flow in 2-3 sentences"\n'
            "}\n\n"
            "IMPORTANT: Mermaid code must be a single string with \\n for newlines. "
            "Use simple alphanumeric node IDs. "
            "{json_instruction}"
        ),
    },
    "reading_guide": {
        "system": (
            "You are a mentor helping a developer understand a new codebase. "
            "Create a reading guide: which files to read, in what order, and why. "
            "Start from entry points and configuration, then core logic, then utilities. "
            "Each step should say WHAT to look for, not just WHICH files. {lang}"
        ),
        "user": (
            "## File Importance Rankings (by PageRank)\n{rankings}\n\n"
            "## Module Summaries\n{module_summaries}\n\n"
            "Create a reading guide with 5-10 steps. Output JSON:\n"
            "{\n"
            '  "introduction": "brief intro on how to approach this codebase",\n'
            '  "steps": [\n'
            '    {"order": 1, "title": "step title", "files": ["file1.py", "file2.py"], '
            '"explanation": "what to look for and why", "time_estimate": "5 min"}\n'
            '  ],\n'
            '  "tips": ["general tip 1", "general tip 2"]\n'
            "}\n\n"
            "{json_instruction}"
        ),
    },
    "chat": {
        "system": (
            "You are a knowledgeable developer answering questions about a codebase. "
            "Answer based on the actual code shown below, not general knowledge. "
            "Reference specific files and line numbers when relevant. "
            "Be direct -- answer the question, don't give a lecture. {lang}"
        ),
        "user": "## Relevant Code\n{context_chunks}\n\n## Question\n{question}",
    },
}


def _load_raw_overrides() -> dict:
    """read the user overrides file if it exists. returns {} on any failure."""
    if not _PROMPTS_FILE.exists():
        return {}
    try:
        data = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_effective_prompts() -> dict[str, dict[str, str]]:
    """return defaults deep-merged with user overrides (override wins)."""
    merged = copy.deepcopy(DEFAULT_PROMPTS)
    overrides = _load_raw_overrides()
    for key in PROMPT_KEYS:
        if key in overrides and isinstance(overrides[key], dict):
            for role in ("system", "user"):
                val = overrides[key].get(role)
                if isinstance(val, str) and val.strip():
                    merged[key][role] = val
    return merged


def save_custom_prompts(prompts: dict) -> None:
    """persist user prompt overrides to ~/.repowiki/prompts.json."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # only keep recognized keys/roles, and only keep non-default values
    clean: dict[str, dict[str, str]] = {}
    for key in PROMPT_KEYS:
        entry = prompts.get(key)
        if not isinstance(entry, dict):
            continue
        roles: dict[str, str] = {}
        for role in ("system", "user"):
            val = entry.get(role)
            if isinstance(val, str):
                roles[role] = val
        if roles:
            clean[key] = roles
    _PROMPTS_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def reset_custom_prompts() -> bool:
    """delete the overrides file. returns True if something was removed."""
    if _PROMPTS_FILE.exists():
        try:
            _PROMPTS_FILE.unlink()
            return True
        except OSError:
            return False
    return False


def _template(key: str) -> tuple[str, str]:
    """fetch the (system, user) template currently in effect for a key."""
    prompts = get_effective_prompts()
    entry = prompts[key]
    return entry["system"], entry["user"]


def _render(system_tpl: str, user_tpl: str, user_vars: dict, language: str) -> list[dict]:
    """fill both templates. {lang} is reserved for the language instruction and is
    injected automatically; user_vars must not contain a 'lang' key."""
    ctx = {**user_vars, "lang": _lang_instruction(language), "json_instruction": _JSON_INSTRUCTION}
    return [
        {"role": "system", "content": system_tpl.format(**ctx)},
        {"role": "user", "content": user_tpl.format(**ctx)},
    ]


def build_overview_prompt(file_tree: str, key_files: str, language: str = "en") -> list[dict]:
    system_tpl, user_tpl = _template("overview")
    return _render(system_tpl, user_tpl, {"file_tree": file_tree, "key_files": key_files}, language)


def build_module_prompt(
    module_name: str,
    files_context: str,
    project_summary: str,
    language: str = "en",
) -> list[dict]:
    system_tpl, user_tpl = _template("module")
    return _render(
        system_tpl,
        user_tpl,
        {"module_name": module_name, "files_context": files_context, "project_summary": project_summary},
        language,
    )


def build_architecture_prompt(
    file_tree: str,
    key_files: str,
    language: str = "en",
) -> list[dict]:
    system_tpl, user_tpl = _template("architecture")
    return _render(system_tpl, user_tpl, {"file_tree": file_tree, "key_files": key_files}, language)


def build_reading_guide_prompt(
    rankings: str,
    module_summaries: str,
    language: str = "en",
) -> list[dict]:
    system_tpl, user_tpl = _template("reading_guide")
    return _render(
        system_tpl, user_tpl, {"rankings": rankings, "module_summaries": module_summaries}, language
    )


def build_chat_prompt(
    question: str,
    context_chunks: str,
    language: str = "en",
) -> list[dict]:
    system_tpl, user_tpl = _template("chat")
    return _render(system_tpl, user_tpl, {"question": question, "context_chunks": context_chunks}, language)


def extract_json(text: str) -> dict | list | None:
    """extract JSON from LLM output, handling markdown fences and extra text."""
    # strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip(), flags=re.MULTILINE)

    # try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # find the first { or [ and match to the last } or ]
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        end = text.rfind(end_char)
        if end == -1 or end <= start:
            continue
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            continue

    return None
