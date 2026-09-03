"""Pydantic models for structured animation plans."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SceneAction(BaseModel):
    action: str
    text: str | None = None
    values: list[Any] | None = None
    index: int | None = None
    label: str | None = None
    node: int | float | str | None = None
    from_node: int | float | str | None = Field(default=None, alias="from")
    to_node: int | float | str | None = Field(default=None, alias="to")
    tree: dict[str, Any] | None = None
    nodes: list[Any] | None = None
    edges: list[Any] | None = None
    directed: bool | None = None
    variables: dict[str, Any] | None = None
    caption: str | None = None
    graph: dict[str, Any] | None = None
    layout: dict[str, Any] | None = None
    weight: int | float | str | None = None
    distances: dict[str, Any] | None = None
    path: list[Any] | None = None

    model_config = {"populate_by_name": True}


class AnimationPlan(BaseModel):
    algorithm: str | None = None
    title: str
    data_structure: str | None = None
    description: str | None = None
    scenes: list[SceneAction]

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "title": self.title,
            "data_structure": self.data_structure,
            "description": self.description,
            "scenes": [
                scene.model_dump(by_alias=True, exclude_none=True)
                for scene in self.scenes
            ],
        }


def validate_animation_plan(data: dict[str, Any]) -> AnimationPlan:
    scenes = [
        SceneAction(**_normalize_scene(scene)) for scene in data.get("scenes", [])
    ]
    return AnimationPlan(
        algorithm=data.get("algorithm"),
        title=data.get("title", "Code Visualization"),
        data_structure=data.get("data_structure"),
        description=data.get("description"),
        scenes=scenes,
    )


def _normalize_scene(scene: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scene, dict):
        return scene
    if scene.get("action") == "show_weighted_graph":
        return _normalize_legacy_weighted_graph_scene(scene)
    if scene.get("action") == "show_graph":
        return _normalize_canonical_graph_scene(scene)
    return scene


def _normalize_legacy_weighted_graph_scene(scene: dict[str, Any]) -> dict[str, Any]:
    graph = scene.get("graph") if isinstance(scene.get("graph"), dict) else scene
    normalized = {
        key: value
        for key, value in scene.items()
        if key not in {"graph", "nodes", "edges", "directed", "layout", "action"}
    }
    normalized["action"] = "show_graph"
    normalized["nodes"] = graph.get("nodes", scene.get("nodes", []))
    normalized["edges"] = _normalize_graph_edges(
        graph.get("edges", scene.get("edges", []))
    )
    if "directed" in graph or "directed" in scene:
        normalized["directed"] = graph.get("directed", scene.get("directed", False))
    if "layout" in graph or "layout" in scene:
        normalized["layout"] = graph.get("layout", scene.get("layout", {}))
    return normalized


def _normalize_canonical_graph_scene(scene: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(scene)
    if "edges" in normalized:
        normalized["edges"] = _normalize_graph_edges(normalized.get("edges", []))
    return normalized


def _normalize_graph_edges(edges: Any) -> list[Any]:
    if not isinstance(edges, list):
        return []

    normalized: list[dict[str, Any]] = []
    for edge in edges:
        if isinstance(edge, dict):
            source = edge.get("from")
            target = edge.get("to")
            if source is None or target is None:
                continue
            item = dict(edge)
            item["from"] = source
            item["to"] = target
            normalized.append(item)
            continue

        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            item: dict[str, Any] = {"from": edge[0], "to": edge[1]}
            if len(edge) >= 3 and edge[2] is not None:
                item["weight"] = edge[2]
            normalized.append(item)

    return normalized
