"""Pydantic models for strategist / planner LLM phases (no coordinates)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DiagramArchetype = Literal["process", "system", "hierarchy", "timeline", "comparison"]

NodeType = Literal["main", "secondary", "small"]


def _coerce_planner_node_type(v: Any) -> str:
    if v is None or v == "":
        return "secondary"
    s = str(v).lower().strip()
    if s in ("main", "secondary", "small"):
        return s
    if s in ("step", "milestone", "hub", "process", "central", "primary", "stage"):
        return "main"
    if s in ("note", "detail", "caption", "footnote", "badge", "tag"):
        return "small"
    return "secondary"


class StrategistOutput(BaseModel):
    """Agent 1 output — semantics only, positions live in the layout engine."""

    diagram_type: DiagramArchetype
    aha_moment: str = Field(min_length=1, max_length=2000)
    core_message: str = Field(min_length=1, max_length=600)
    components: list[str] = Field(min_length=2, max_length=32)


class PlannerNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=200)
    type: NodeType = "secondary"
    emphasis: bool = False

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> str:
        return _coerce_planner_node_type(v)


class PlannerEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    from_id: str = Field(alias="from", min_length=1, max_length=64)
    to: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=200)


class PlannerGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    node_ids: list[str] = Field(min_length=1, max_length=24)


class PlannerOutput(BaseModel):
    """Agent 2 output — graph only (no x/y/width/height)."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[PlannerNode] = Field(min_length=2, max_length=48)
    edges: list[PlannerEdge] = Field(default_factory=list, max_length=96)
    groups: list[PlannerGroup] = Field(default_factory=list, max_length=12)


class LayoutBox(BaseModel):
    """Deterministic layout result for one graph node."""

    model_config = ConfigDict(extra="forbid")

    id: str
    x: float
    y: float
    width: float
    height: float


class LayoutConfig(BaseModel):
    """Knobs for deterministic layouts — LLM never emits these numbers."""

    horizontal_gap: float = Field(default=200.0, ge=40.0, le=600.0)
    vertical_gap: float = Field(default=120.0, ge=40.0, le=500.0)
    padding: float = Field(default=80.0, ge=20.0, le=300.0)
    spacing_multiplier: float = Field(default=1.0, gt=0.05, le=6.0)
    title_band: float = Field(default=100.0, ge=60.0, le=200.0)
    layout_archetype: DiagramArchetype


class GeometryIssue(BaseModel):
    """One geometric validation hit (deterministic validator)."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=40)
    severity: str = Field(max_length=12)
    detail: str = Field(max_length=500)
    node_ids: list[str] = Field(default_factory=list, max_length=16)


Severity = Literal["high", "medium", "low"]


class StructuredCriticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=64)
    severity: Severity


class VisualCriticOutput(BaseModel):
    """Vision multimodal critic — score + actionable layout intents."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=10)
    issues: list[StructuredCriticIssue] = Field(default_factory=list, max_length=24)
    layout_actions: list[str] = Field(default_factory=list, max_length=32)
    suggestions: list[str] = Field(default_factory=list, max_length=40)


class AgentTokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class DiagramBrandTheme(BaseModel):
    """Brand palette — every rendered color must resolve from these tokens."""

    primary: str = Field(default="#3B82F6", min_length=4, max_length=32)
    secondary: str = Field(default="#64748B", min_length=4, max_length=32)
    accent: str = Field(default="#F59E0B", min_length=4, max_length=32)
    text: str = Field(default="#F1F5F9", min_length=4, max_length=32)
    background: str = Field(default="#0F172A", min_length=4, max_length=32)
    font: str = Field(default="Inter", min_length=1, max_length=120)


class NodeLayoutDebug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    x: float
    y: float
    width: float
    height: float
    type: str


class IterationDebug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_type: DiagramArchetype
    geometry_issue_count: int
    geometry_issues: list[str] = Field(default_factory=list, max_length=96)


class DiagramPipelineDebug(BaseModel):
    strategist: StrategistOutput
    planner_versions: list[PlannerOutput]
    layout_configs_per_iteration: list[LayoutConfig]
    geometry_issues_per_iteration: list[list[GeometryIssue]]
    critic_runs: list[VisualCriticOutput]
    final_score: int
    iterations_used: int
    token_usage: AgentTokenUsage
    render_png_paths_per_iteration: list[str] = Field(default_factory=list, max_length=8)
    brand_theme: DiagramBrandTheme | None = None
    node_layout_final: list[NodeLayoutDebug] = Field(default_factory=list, max_length=64)
    edges_final: list[dict[str, str]] = Field(default_factory=list, max_length=96)
    iteration_debug: list[IterationDebug] = Field(default_factory=list, max_length=8)
