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
            "scenes": [scene.model_dump(by_alias=True, exclude_none=True) for scene in self.scenes],
        }


def validate_animation_plan(data: dict[str, Any]) -> AnimationPlan:
    scenes = [SceneAction(**scene) for scene in data.get("scenes", [])]
    return AnimationPlan(
        algorithm=data.get("algorithm"),
        title=data.get("title", "Code Visualization"),
        data_structure=data.get("data_structure"),
        description=data.get("description"),
        scenes=scenes,
    )
