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
PROMPT_KEYS = ("overview", "business_process", "architecture", "data_flow", "reading_guide", "chat")


def _lang_instruction(language: str) -> str:
    lang_map = {
        "en": "Write ALL output (descriptions, explanations, field values) in English.",
        "zh": (
            "重要：你必须用中文撰写全部输出内容，包括描述、解释、字段值。"
            "JSON 的 key 保持英文，但所有 value（description、purpose、explanation 等）"
            "必须用中文。代码片段、类名、函数名、文件路径保持原文不翻译。"
            "绝对不要用英文写描述性内容。"
        ),
        "ja": "すべての出力内容（説明、フィールド値）を日本語で書いてください。JSONのキーは英語のまま、値は日本語にしてください。",
        "ko": "모든 출력 내용(설명, 필드 값)을 한국어로 작성해 주세요. JSON 키는 영어로, 값은 한국어로.",
    }
    return lang_map.get(language, "Write ALL output in English.")


_JSON_INSTRUCTION = (
    "只输出合法的 JSON，不要加 markdown 代码围栏，不要在 JSON 前后加任何解释文字，"
    "只输出 JSON 对象本身。"
)

# 代码安全约束：wiki 是文档库，不是代码仓库。
# 可以引用代码片段说明逻辑，但不得大段原样输出源码。
_CODE_SAFETY = (
    "重要：这是技术文档，不是代码仓库。你可以在描述中引用简短的代码片段（3-5行）"
    "来解释关键逻辑，但绝对不要把整份源码或大段代码（超过10行）原样复制到文档中。"
    "要看完整代码的读者应该自己去拉取代码。你的职责是解释和理解，不是搬运代码。"
)

# Default templates. Placeholders: {lang}, {json_instruction}, {code_safety},
# {custom_instructions} are auto-injected; domain variables ({file_tree}, etc.)
# are filled by each builder.
DEFAULT_PROMPTS: dict[str, dict[str, str]] = {
    "overview": {
        "system": (
            "你是一位资深软件工程师和业务分析师，正在向新团队成员介绍一个项目。"
            "你需要同时从业务视角（解决什么问题、谁在使用、核心用例）和技术视角"
            "（架构、技术栈）来分析项目。要直接、具体、言之有物，不要用空话套话。"
            "如果项目涉及重要公式（评分、排序、定价、风控、机器学习指标等），"
            "务必提取并解释。{code_safety}"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": (
            "分析这个项目的代码。如果之前已扫描过，重点关注新增或变更部分。\n\n"
            "## 文件树\n```\n{file_tree}\n```\n\n"
            "## 关键文件\n{key_files}\n\n"
            "{supplementary_docs}"
            "生成项目概览，输出 JSON：\n"
            "{\n"
            '  "name": "项目名称",\n'
            '  "one_liner": "一句话描述项目做什么（不超过20字）",\n'
            '  "description": "3-4段：(1) 业务背景和解决的问题，(2) 端到端业务流程——'
            '请求如何进入、经过哪些处理阶段、最终输出什么，(3) 核心数据实体及其在系统中的流转",\n'
            '  "tech_stack": [{"name": "Python", "category": "language|framework|database|tool", "version": "3.10+"}],\n'
            '  "setup_instructions": ["步骤1", "步骤2"],\n'
            '  "key_features": ["核心功能1", "核心功能2"],\n'
            '  "business_cases": [\n'
            '    "详细的业务场景：触发条件、流程、参与者、结果",\n'
            '  ],\n'
            '  "formulas": [\n'
            '    {"name": "公式名称", "expression": "score = tf * log(N / df)", '
            '"explanation": "计算什么、每个变量的含义、业务上为什么重要"}\n'
            '  ]\n'
            "}\n\n"
            "要求：\n"
            "- description：必须追踪端到端业务流程，不要只列举功能。"
            "如果有补充文档，用它来建立代码概念和业务术语之间的映射。\n"
            "- business_cases：把每个场景描述为一个流程（触发→处理→结果），包含参与者和业务含义。\n"
            "- formulas：包含所有重要公式（交易策略、定价、评分、风控、ML指标）。"
            "逐一解释每个变量和业务上下文。确实没有才留空。\n"
            "- 如果提供了补充文档，必须用它来丰富理解——它可能包含代码里看不出来的"
            "业务术语、领域规则或流程描述。{json_instruction}"
        ),
    },
    "module": {
        "system": (
            "你是一位资深工程师兼领域专家，正在做深入的代码审查并撰写文档。"
            "要直接、具体、有深度，不要空话。"
            "对每个模块解释：每个文件做什么、文件之间如何交互（调用链、数据传递、"
            "事件、消息队列）、关键函数/类是什么。"
            "重要：追踪核心业务逻辑的端到端流程——什么数据进入、如何转换、"
            "应用了什么业务规则、产出什么结果或副作用。解释「为什么」，不只是「是什么」。"
            "同时识别潜在问题（bug、竞态条件、异常处理缺陷、安全风险、代码异味）"
            "和具体的优化建议（性能、可维护性、可扩展性）。要诚实、具体，引用文件名和函数名。"
            "{code_safety}"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": (
            "项目：{project_summary}\n\n"
            "{supplementary_docs}"
            "深入分析 '{module_name}' 模块。以下是它的文件：\n\n"
            "{files_context}\n\n"
            "输出 JSON：\n"
            "{\n"
            '  "name": "{module_name}",\n'
            '  "purpose": "一句话说明该模块的职责",\n'
            '  "description": "详细说明模块的角色、业务背景、端到端工作方式",\n'
            '  "business_logic": "逐步追踪核心业务流程：什么数据/请求进入，如何处理'
            '（转换、业务规则、校验），做了什么决策，产出什么结果/副作用。引用具体的类和方法名。",\n'
            '  "files": [\n'
            '    {"path": "file.py", "purpose": "在业务上下文中做什么", '
            '"key_symbols": [{"name": "func_name", "kind": "function", "description": '
            '"详细说明：做什么、参数、返回值、业务含义"}]}\n'
            '  ],\n'
            '  "relationships": [{"source": "a.py", "target": "b.py", "description": "a 调用 b 来..."}],\n'
            '  "key_concepts": [{"name": "概念名", "explanation": "结合业务上下文的详细解释"}],\n'
            '  "potential_issues": [\n'
            '    "具体的问题/风险，引用文件和函数，例如：user_service.py:login() 没有限流"\n'
            '  ],\n'
            '  "optimization_points": [\n'
            '    "具体的改进建议，引用文件，例如：db.py:query() 存在 N+1 查询，应批量处理"\n'
            '  ]\n'
            "}\n\n"
            "要求：\n"
            "- business_logic：这是最重要的字段，不可跳过。用具体方法名追踪完整的"
            "数据/业务流程。例如交易模块：订单如何进入、策略如何选择、执行如何工作、"
            "行情数据如何使用、状态如何转换。\n"
            "- key_symbols：描述每个符号的业务含义，不只是技术签名。\n"
            "- relationships：描述文件之间如何交互（谁调用谁、数据流向、事件订阅），"
            "不只是 import 关系。\n"
            "- potential_issues：具体并引用位置。确实没有才留空。\n"
            "- optimization_points：可操作的改进建议。确实没有才留空。{json_instruction}"
        ),
    },
    "business_process": {
        "system": (
            "你是一位资深业务分析师和架构师，正在梳理项目的核心业务流程。"
            "从代码中识别出最主要的前 3-7 个业务流程/工作流，"
            "对每个流程追踪：什么触发它、经过哪些处理步骤、涉及哪些关键类和方法、"
            "最终产出什么结果。用业务语言描述，同时引用具体的代码位置。"
            "不要只列举功能点，要描述流程的完整运转方式。{code_safety}"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": (
            "## 文件树\n```\n{file_tree}\n```\n\n"
            "## 关键文件\n{key_files}\n\n"
            "{supplementary_docs}"
            "识别项目的核心业务流程。输出 JSON：\n"
            "{\n"
            '  "introduction": "概述这个项目的业务流程整体框架",\n'
            '  "processes": [\n'
            '    {\n'
            '      "order": 1,\n'
            '      "title": "流程名称（业务术语）",\n'
            '      "trigger": "什么触发这个流程（用户操作/定时任务/事件/消息）",\n'
            '      "flow": "逐步描述处理过程：数据如何进入→经过哪些处理/转换/校验→'
            '应用了什么业务规则→做了什么决策。引用具体的类和方法名。",\n'
            '      "outcome": "流程的结果或副作用",\n'
            '      "key_methods": ["ClassName.methodName()", "AnotherClass.otherMethod()"]\n'
            '    }\n'
            '  ]\n'
            "}\n\n"
            "要求：\n"
            "- 识别 3-7 个最核心的业务流程，不要列举无关紧要的工具方法。\n"
            "- flow 字段是核心——要像讲故事一样描述流程的完整运转，"
            "不是简单罗列。例如：「用户下单→OrderService.create() 校验参数→"
            "BasketAOImpl.openBasket() 创建篮子→enterOrder 队列按 200ms 间隔发送子订单→...」\n"
            "- 如果有补充文档，用它来确认业务流程的准确性和术语。{json_instruction}"
        ),
    },
    "data_flow": {
        "system": (
            "你是一位数据架构师，正在分析项目的核心数据流转规则。"
            "追踪主要数据实体从输入到持久化的完整路径："
            "数据从哪进入系统、经过哪些转换步骤、在什么环节被校验/加工/聚合、"
            "最终存到哪里或发送到哪里。生成清晰的 Mermaid 数据流图。{code_safety}"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": (
            "## 文件树\n```\n{file_tree}\n```\n\n"
            "## 关键文件\n{key_files}\n\n"
            "{supplementary_docs}"
            "分析核心数据流。输出 JSON：\n"
            "{\n"
            '  "summary": "2-3段描述整体数据流架构：数据从哪来、怎么流转、存到哪去",\n'
            '  "mermaid": "graph LR\\n  A[数据源] --> B[处理] --> C[存储]\\n  ...",\n'
            '  "entities": ["核心数据实体1（如：订单Order）", "核心数据实体2（如：行情MarketData）"],\n'
            '  "transformations": [\n'
            '    "数据转换步骤1：例如 行情数据从网关接收后，经过QuoteProcessor.normalize()标准化",\n'
            '    "数据转换步骤2：例如 订单经过风控校验后，由OrderMapper插入数据库"\n'
            '  ]\n'
            "}\n\n"
            "要求：\n"
            "- mermaid：画一个数据流图（graph LR），展示数据从源到终点的流转路径。"
            "用中文标签，节点ID用字母数字。单个字符串，用 \\n 换行。\n"
            "- entities：列出核心业务数据实体（不只是数据库表名，要有业务含义）。\n"
            "- transformations：逐步描述数据在流转中如何被加工。引用具体的处理类和方法。"
            "{json_instruction}"
        ),
    },
    "architecture": {
        "system": (
            "你是一位软件架构师，正在分析一个代码库。"
            "识别架构模式、梳理组件及其交互方式、描述主数据流、"
            "盘点所有外部依赖（运行时连接的服务：数据库、缓存、消息队列、第三方API；"
            "以及构建所用的框架/库：Web框架、ORM等）。"
            "生成合法的 Mermaid 图表，使用简单的节点名。{code_safety}"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": (
            "## 文件树\n```\n{file_tree}\n```\n\n"
            "## 关键文件\n{key_files}\n\n"
            "{supplementary_docs}"
            "分析架构。输出 JSON：\n"
            "{\n"
            '  "architecture_type": "monolith/client-server/microservices/library/cli-tool/framework/plugin-system/pipeline 之一",\n'
            '  "description": "解释架构、组件交互、请求/数据流（2-4句）",\n'
            '  "components": [{"name": "...", "purpose": "...", "files": ["..."]}],\n'
            '  "mermaid_component": "graph TD\\n  A[组件] --> B[组件]\\n  ...",\n'
            '  "mermaid_sequence": "sequenceDiagram\\n  participant A\\n  A->>B: 请求\\n  ...",\n'
            '  "data_flow": "端到端描述主数据流：数据从哪进入、如何转换、持久化到哪里",\n'
            '  "service_dependencies": [\n'
            '    {"name": "PostgreSQL", "category": "database|cache|message-queue|'
            'search|third-party-api|object-storage", "purpose": "主事务存储"}\n'
            '  ],\n'
            '  "framework_dependencies": [\n'
            '    {"name": "FastAPI", "category": "web-framework|orm|task-queue|'
            'auth|serialization|testing", "purpose": "提供 REST API"}\n'
            '  ]\n'
            "}\n\n"
            "重要：Mermaid 代码必须是单个字符串，用 \\n 表示换行。使用简单的字母数字节点ID。\n"
            "- service_dependencies：运行时连接的外部系统（从配置、连接代码、环境变量中识别）。\n"
            "- framework_dependencies：构建所用的库/框架（从依赖文件、import 中识别）。"
            "{json_instruction}"
        ),
    },
    "reading_guide": {
        "system": (
            "你是一位导师，帮助开发者理解一个新代码库。"
            "创建一份阅读指南：先读哪些文件、按什么顺序、为什么。"
            "从入口点和配置开始，然后是核心业务逻辑和数据模型，最后是辅助工具。"
            "每一步要说清楚「看什么」和「为什么重要」，而不只是「看哪个文件」。"
            "{code_safety}"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": (
            "## 文件重要性排名（按 PageRank）\n{rankings}\n\n"
            "## 模块摘要\n{module_summaries}\n\n"
            "创建一份 5-10 步的阅读指南。输出 JSON：\n"
            "{\n"
            '  "introduction": "简要介绍如何入手这个代码库",\n'
            '  "steps": [\n'
            '    {"order": 1, "title": "步骤标题", "files": ["file1.py", "file2.py"], '
            '"explanation": "看什么、为什么重要", "time_estimate": "5分钟"}\n'
            '  ],\n'
            '  "tips": ["通用建议1", "通用建议2"]\n'
            "}\n\n"
            "{json_instruction}"
        ),
    },
    "chat": {
        "system": (
            "你是一位资深开发者，正在回答关于某个代码库的问题。"
            "下方的上下文可能包含两部分：\n"
            "1.「Wiki 分析」——之前生成的业务逻辑分析，追踪了跨文件的数据流和业务规则。"
            "回答业务逻辑、数据流、「X 是怎么工作的」这类问题时，以此为主要信息来源。\n"
            "2.「相关代码」——按关键词检索到的原始代码片段。"
            "用于具体的实现细节、变量名、行号引用。\n"
            "基于提供的上下文回答，不要凭空泛知识。引用具体的文件、方法、行号。"
            "被问到业务逻辑时，逐步追踪完整流程：什么触发它、用了什么数据、"
            "有哪些分支决策、结果是什么。要全面但直接。{code_safety}"
            "\n\n"
            "深度追问识别：如果用户的问题明确要求对某个主题做深入/细致的分析"
            "（比如出现「详细解释」「深入分析」「具体怎么实现」「完整流程」等词），"
            "且你认为当前上下文不足以给出充分回答，请在回答的开头输出一行特殊标记：\n"
            "[DEEP_DIVE_SUGGEST]关键词1, 关键词2, 关键词3[/DEEP_DIVE_SUGGEST]\n"
            "其中关键词是你建议用来重新检索代码的扩展搜索词（英文标识符和中文术语都可以）。"
            "输出标记后，继续基于已有上下文给出你的初步回答。"
            "如果当前上下文已经足够回答，就不要输出这个标记。"
            "{custom_instructions}"
            "{lang}"
        ),
        "user": "{context_chunks}\n\n## 问题\n{question}",
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


def _render(
    system_tpl: str, user_tpl: str, user_vars: dict, language: str,
    custom_instructions: str = "",
) -> list[dict]:
    """fill both templates by substituting named {placeholders}.

    Uses targeted string replacement rather than str.format() so that literal
    braces in the template (e.g. JSON examples like {"name": ...}) are left
    untouched. Only known variable names are substituted.
    """
    ci = (custom_instructions or "").strip()
    if ci:
        ci = "\n额外要求（用户针对本次扫描的特别指示）：\n" + ci + "\n"
    substitutions = {
        **user_vars,
        "lang": _lang_instruction(language),
        "json_instruction": _JSON_INSTRUCTION,
        "code_safety": _CODE_SAFETY,
        "custom_instructions": ci,
    }

    def _fill(tpl: str) -> str:
        result = tpl
        for name, value in substitutions.items():
            result = result.replace("{" + name + "}", value)
        return result

    return [
        {"role": "system", "content": _fill(system_tpl)},
        {"role": "user", "content": _fill(user_tpl)},
    ]


def _fmt_supplementary(docs: str) -> str:
    """format supplementary docs into a prompt section, or empty string."""
    docs = (docs or "").strip()
    if not docs:
        return ""
    return (
        "## 补充文档（用户提供的业务上下文）\n"
        "用户提供了以下文档来帮助理解项目。它可能包含业务术语、领域规则、"
        "流程描述或产品规格——这些从代码里可能看不出来。用它来建立代码标识符"
        "和业务概念之间的桥梁。\n\n"
        f"{docs}\n\n"
    )


def build_overview_prompt(
    file_tree: str, key_files: str, language: str = "en",
    supplementary_docs: str = "", custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("overview")
    return _render(
        system_tpl, user_tpl,
        {"file_tree": file_tree, "key_files": key_files,
         "supplementary_docs": _fmt_supplementary(supplementary_docs)},
        language, custom_instructions,
    )


def build_module_prompt(
    module_name: str, files_context: str, project_summary: str,
    language: str = "en", supplementary_docs: str = "", custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("module")
    return _render(
        system_tpl, user_tpl,
        {"module_name": module_name, "files_context": files_context,
         "project_summary": project_summary,
         "supplementary_docs": _fmt_supplementary(supplementary_docs)},
        language, custom_instructions,
    )


def build_architecture_prompt(
    file_tree: str, key_files: str, language: str = "en",
    supplementary_docs: str = "", custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("architecture")
    return _render(
        system_tpl, user_tpl,
        {"file_tree": file_tree, "key_files": key_files,
         "supplementary_docs": _fmt_supplementary(supplementary_docs)},
        language, custom_instructions,
    )


def build_reading_guide_prompt(
    rankings: str, module_summaries: str, language: str = "en",
    custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("reading_guide")
    return _render(
        system_tpl, user_tpl,
        {"rankings": rankings, "module_summaries": module_summaries},
        language, custom_instructions,
    )


def build_business_process_prompt(
    file_tree: str, key_files: str, language: str = "en",
    supplementary_docs: str = "", custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("business_process")
    return _render(
        system_tpl, user_tpl,
        {"file_tree": file_tree, "key_files": key_files,
         "supplementary_docs": _fmt_supplementary(supplementary_docs)},
        language, custom_instructions,
    )


def build_data_flow_prompt(
    file_tree: str, key_files: str, language: str = "en",
    supplementary_docs: str = "", custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("data_flow")
    return _render(
        system_tpl, user_tpl,
        {"file_tree": file_tree, "key_files": key_files,
         "supplementary_docs": _fmt_supplementary(supplementary_docs)},
        language, custom_instructions,
    )


def build_deep_dive_prompt(
    question: str, context_chunks: str, language: str = "en",
    custom_instructions: str = "",
) -> list[dict]:
    """prompt for a deep-dive analysis on a specific topic.

    Unlike chat (which answers from existing context), deep-dive instructs the
    LLM to produce a thorough standalone analysis suitable for a wiki page.
    """
    system_tpl, user_tpl = _template("chat")
    # override: deep-dive is a one-shot thorough analysis, not a Q&A
    system_override = (
        "你正在对代码库的某个主题做深入专题分析，结果将作为 wiki 页面持久化。"
        "基于提供的代码片段和 Wiki 分析，写一份结构化的深入分析文档（markdown 格式）。"
        "包括：该主题的完整流程、核心逻辑、关键类和方法、数据流转、"
        "边界条件和异常处理。引用具体的文件名和方法名。"
        "用中文撰写（代码标识符保持原文）。{code_safety}"
        "{custom_instructions}"
        "{lang}"
    )
    user_override = (
        "## 相关代码与分析上下文\n{context_chunks}\n\n"
        "## 分析要求\n{question}\n\n"
        "请写一份深入的专题分析（markdown 格式，适合作为 wiki 页面）。"
    )
    return _render(
        system_override, user_override,
        {"context_chunks": context_chunks, "question": question},
        language, custom_instructions,
    )


def build_chat_prompt(
    question: str, context_chunks: str, language: str = "en",
    custom_instructions: str = "",
) -> list[dict]:
    system_tpl, user_tpl = _template("chat")
    return _render(
        system_tpl, user_tpl,
        {"question": question, "context_chunks": context_chunks},
        language, custom_instructions,
    )


def extract_json(text: str) -> dict | list | None:
    """extract JSON from LLM output, handling markdown fences and extra text."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip(), flags=re.MULTILINE)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

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
