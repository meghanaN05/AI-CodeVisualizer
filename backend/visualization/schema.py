"""Visualization DSL — the contract between planner and renderer.

The LLM (or a rule-based agent) emits this language. It never emits Manim.
Coordinates are filled later by the layout engine, not by the planner.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ALLOWED_ACTIONS = frozenset(
    {
        "show_title",
        "show_caption",
        "show_graph",
        "show_weighted_graph",
        "visit",
        "visit_node",
        "relax",
        "relax_edge",
        "update_distance",
        "show_shortest_path",
        "highlight",
        "highlight_node",
        "highlight_edge",
        "highlight_index",
        "highlight_component",
        "create_array",
        "compare_indices",
        "swap_indices",
        "show_tree",
        "move_pointer",
        "push_stack",
        "pop_stack",
        "show_variables",
        "show_architecture",
        "show_flow",
        "show_class_methods",
        "show_hashmap",
        "hashmap_insert",
        "show_heap",
        "heap_push",
        "heap_pop",
        "show_method_flow",
        "chapter",
    }
)


class DslNode(BaseModel):
    id: str
    label: str | None = None
    category: str | None = None


class DslEdge(BaseModel):
    model_config = {"populate_by_name": True}

    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    weight: int | float | str | None = None
    label: str | None = None


class DslStep(BaseModel):
    model_config = {"populate_by_name": True}

    action: str
    node: str | int | float | None = None
    edge: list[str] | None = None
    from_id: str | None = Field(default=None, alias="from")
    to_id: str | None = Field(default=None, alias="to")
    weight: int | float | str | None = None
    caption: str | None = None
    text: str | None = None
    label: str | None = None
    index: int | None = None
    values: list[Any] | None = None
    variables: dict[str, Any] | None = None
    distances: dict[str, Any] | None = None
    path: list[Any] | None = None
    nodes: list[Any] | None = None
    edges: list[Any] | None = None
    directed: bool | None = None
    tree: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None
    component: str | None = None
    chapter: str | None = None


class Chapter(BaseModel):
    id: str
    title: str
    caption: str | None = None
    steps: list[DslStep] = Field(default_factory=list)


class ComplexityReport(BaseModel):
    nodes: int = 0
    edges: int = 0
    methods: int = 0
    classes: int = 0
    steps: int = 0
    scenes_required: int = 1
    complexity: Literal["low", "medium", "high"] = "low"


class VisualizationDocument(BaseModel):
    """Canonical visualization plan. Planner output. Renderer input after layout."""

    domain: Literal["graph", "tree", "array", "system_design", "generic"] = "generic"
    type: str = "generic"
    algorithm: str | None = None
    title: str = "Code Visualization"
    description: str | None = None
    data_structure: str | None = None
    nodes: list[DslNode] = Field(default_factory=list)
    edges: list[DslEdge] = Field(default_factory=list)
    components: list[DslNode] = Field(default_factory=list)
    connections: list[DslEdge] = Field(default_factory=list)
    tree: dict[str, Any] | None = None
    values: list[Any] | None = None
    layout: dict[str, list[float]] = Field(default_factory=dict)
    chapters: list[Chapter] = Field(default_factory=list)
    steps: list[DslStep] = Field(default_factory=list)
    complexity: ComplexityReport | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


def document_from_dict(data: dict[str, Any]) -> VisualizationDocument:
    payload = dict(data)
    if "from" in payload and "from_id" not in payload:
        pass
    return VisualizationDocument.model_validate(payload)
