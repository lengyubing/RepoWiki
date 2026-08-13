"""data models for repowiki analysis pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """metadata about a single file in the project."""

    path: str
    size: int
    language: str = "unknown"
    lines: int = 0
    preview: str = ""
    content: str = ""
    is_config: bool = False
    is_entrypoint: bool = False


class ProjectContext(BaseModel):
    """everything we know about a project before LLM analysis."""

    name: str
    root: str
    files: list[FileInfo] = Field(default_factory=list)
    file_tree: str = ""
    supplementary_docs: str = ""  # user-provided business docs to enrich LLM context
    custom_instructions: str = ""  # per-scan special prompt instructions

    @property
    def total_lines(self) -> int:
        return sum(f.lines for f in self.files)


# --- LLM analysis output models ---


class TechItem(BaseModel):
    name: str
    category: str = ""  # language, framework, database, etc.
    version: str = ""


class Formula(BaseModel):
    """an important business/algorithmic formula worth surfacing in the docs."""
    name: str = ""
    expression: str = ""  # the formula itself, e.g. "score = tf * log(N / df)"
    explanation: str = ""


class ProjectOverview(BaseModel):
    name: str = ""
    one_liner: str = ""
    description: str = ""
    tech_stack: list[TechItem] = Field(default_factory=list)
    setup_instructions: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    business_cases: list[str] = Field(default_factory=list)  # main business use cases
    formulas: list[Formula] = Field(default_factory=list)  # important formulas


class Symbol(BaseModel):
    name: str
    kind: str = ""  # function, class, variable, constant
    line: int = 0
    description: str = ""


class FileDoc(BaseModel):
    path: str
    purpose: str = ""
    key_symbols: list[Symbol] = Field(default_factory=list)


class Relationship(BaseModel):
    source: str
    target: str
    description: str = ""


class Concept(BaseModel):
    name: str
    explanation: str = ""


class ModuleDoc(BaseModel):
    name: str
    purpose: str = ""
    description: str = ""
    business_logic: str = ""  # end-to-end business/data flow trace
    files: list[FileDoc] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    key_concepts: list[Concept] = Field(default_factory=list)
    potential_issues: list[str] = Field(default_factory=list)  # bugs, risks, code smells
    optimization_points: list[str] = Field(default_factory=list)  # perf/quality improvements


class Component(BaseModel):
    name: str
    purpose: str = ""
    files: list[str] = Field(default_factory=list)


class DependencyItem(BaseModel):
    """an external service or framework the project depends on."""
    name: str
    category: str = ""  # e.g. database, message-queue, web-framework, orm
    purpose: str = ""  # what it's used for in this project


class ArchitectureDiagram(BaseModel):
    architecture_type: str = ""  # monolith, client-server, microservices, etc.
    description: str = ""
    components: list[Component] = Field(default_factory=list)
    mermaid_component: str = ""
    mermaid_sequence: str = ""
    data_flow: str = ""
    service_dependencies: list[DependencyItem] = Field(default_factory=list)
    framework_dependencies: list[DependencyItem] = Field(default_factory=list)


class ReadingStep(BaseModel):
    order: int
    title: str
    files: list[str] = Field(default_factory=list)
    explanation: str = ""
    time_estimate: str = ""


class ReadingGuide(BaseModel):
    introduction: str = ""
    steps: list[ReadingStep] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


class ProcessStep(BaseModel):
    """a single business process / workflow in the project."""
    order: int
    title: str = ""
    trigger: str = ""        # what triggers this process
    flow: str = ""           # step-by-step processing description
    outcome: str = ""        # result / side-effects
    key_methods: list[str] = Field(default_factory=list)  # involved classes/methods


class BusinessProcess(BaseModel):
    """the main business processes / workflows in the project."""
    introduction: str = ""
    processes: list[ProcessStep] = Field(default_factory=list)


class DataFlowDetail(BaseModel):
    """detailed data flow analysis, richer than architecture.data_flow."""
    summary: str = ""         # overall data flow narrative
    mermaid: str = ""         # mermaid data-flow diagram
    entities: list[str] = Field(default_factory=list)  # core data entities
    transformations: list[str] = Field(default_factory=list)  # how data transforms at each stage


class WikiData(BaseModel):
    """complete wiki analysis output."""

    overview: ProjectOverview = Field(default_factory=ProjectOverview)
    modules: list[ModuleDoc] = Field(default_factory=list)  # kept for compatibility, no longer primary
    architecture: ArchitectureDiagram = Field(default_factory=ArchitectureDiagram)
    business_process: BusinessProcess = Field(default_factory=BusinessProcess)
    data_flow: DataFlowDetail = Field(default_factory=DataFlowDetail)
    reading_guide: ReadingGuide = Field(default_factory=ReadingGuide)
    file_index: dict[str, FileDoc] = Field(default_factory=dict)
