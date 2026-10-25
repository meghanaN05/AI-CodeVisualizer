"""Unified planning pipeline: analyze IR, classify it, then plan.

Routes graph/tree/system-design inputs through the deterministic
visualization DSL agents (which use the layout engine and collision
detection) and falls back to the legacy rule-based planner for every
other domain (arrays, sorts, recursion, hash maps, classifier leftovers).
"""

from __future__ import annotations

from typing import Any

from ai import generate_animation_plan
from analyzer import analyze
from trace_planner import plan_from_trace
from tracing import trace_code
from visualization.graph import plan_graph
from visualization.layout import apply_layout
from visualization.schema import DslStep, VisualizationDocument
from visualization.system_design import plan_system_design
from visualization.tree import plan_tree
from visualization.validator import validate_document


def build_visualization_plan(code: str, language: str) -> dict[str, Any]:
    """Analyze and plan. Returns the final plan in the renderer's scene shape.

    Executing the snippet and animating its real trace is the primary path;
    the pattern-based planners below only run when no trace is available.
    """
    trace = trace_code(code, language)
    if trace is not None:
        plan = plan_from_trace(trace, code)
        if plan is not None:
            return plan

    ir = analyze(code, language)
    domain = ir.get("classification", {}).get("domain", "generic")

    if domain == "graph":
        doc = plan_graph(ir)
    elif domain == "tree":
        doc = plan_tree(ir)
    elif domain == "system_design":
        doc = plan_system_design(ir)
    else:
        return generate_animation_plan(ir)

    doc = apply_layout(doc)
    doc = validate_document(doc)
    return _document_to_plan(doc)


def _document_to_plan(doc: VisualizationDocument) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    for step in doc.steps:
        scene = _dsl_step_to_scene(doc, step)
        if scene:
            scenes.append(scene)
    return {
        "algorithm": doc.algorithm,
        "title": doc.title,
        "data_structure": doc.data_structure,
        "description": doc.description,
        "scenes": scenes,
    }


_PASSTHROUGH_KEYS: dict[str, set[str]] = {
    "create_array": {"values", "caption"},
    "highlight_index": {"index", "label", "caption"},
    "highlight_range": {"index", "label", "caption"},
    "compare_indices": {"index", "label", "caption"},
    "swap_indices": {"index", "label", "values", "caption"},
    "show_tree": {"tree"},
    "move_pointer": {"from", "to", "caption"},
    "show_variables": {"variables", "caption"},
    "push_stack": {"label", "caption"},
    "pop_stack": {"label", "caption"},
    "show_class_methods": {"text", "nodes", "caption"},
    "show_hashmap": {"text", "values", "caption"},
    "hashmap_insert": {"text", "label", "caption"},
    "show_heap": {"values", "caption"},
    "heap_push": {"label", "caption"},
    "heap_pop": {"label", "caption"},
    "show_method_flow": {"text", "caption"},
}


def _dsl_step_to_scene(
    doc: VisualizationDocument, step: DslStep
) -> dict[str, Any] | None:
    action = step.action
    caption = step.caption

    if action == "show_title":
        return {"action": "show_title", "text": step.text or doc.title}
    if action == "show_caption":
        return {"action": "show_caption", "text": step.text or caption or ""}
    if action == "chapter":
        return {"action": "chapter", "text": step.text or step.chapter or "Chapter"}
    if action == "show_graph":
        scene: dict[str, Any] = {
            "action": "show_graph",
            "nodes": step.nodes or [],
            "edges": step.edges or [],
        }
        if step.directed is not None:
            scene["directed"] = step.directed
        if doc.layout:
            scene["layout"] = doc.layout
        if caption:
            scene["caption"] = caption
        return scene
    if action == "show_tree":
        scene: dict[str, Any] = {"action": "show_tree", "tree": step.tree or {}}
        if doc.layout:
            scene["layout"] = doc.layout
        return scene
    if action == "show_weighted_graph":
        return {
            "action": "show_weighted_graph",
            "graph": step.graph or {
                "nodes": step.nodes or [],
                "edges": step.edges or [],
            },
            "caption": caption,
        }
    if action in {"visit", "visit_node"}:
        return {"action": "visit_node", "node": step.node, "caption": caption}
    if action in {"relax", "relax_edge"}:
        return {
            "action": "relax_edge",
            "from": step.from_id,
            "to": step.to_id,
            "weight": step.weight,
            "caption": caption,
        }
    if action in {"highlight", "highlight_node"}:
        return {"action": "highlight_node", "node": step.node, "caption": caption}
    if action == "highlight_edge":
        return {
            "action": "relax_edge",
            "from": step.from_id,
            "to": step.to_id,
            "weight": step.weight,
            "caption": caption,
        }
    if action == "update_distance":
        return {
            "action": "update_distance",
            "node": step.node,
            "distances": step.distances or {},
            "label": step.label,
            "caption": caption,
        }
    if action == "show_shortest_path":
        return {
            "action": "show_shortest_path",
            "path": step.path or [],
            "graph": {},
            "caption": caption,
        }
    if action == "show_architecture":
        return {
            "action": "show_architecture",
            "components": [
                {
                    "id": comp.id,
                    "label": comp.label or comp.id,
                    "category": comp.category or "other",
                }
                for comp in doc.components
            ],
            "connections": [{"from": e.from_id, "to": e.to_id} for e in doc.connections],
            "layout": doc.layout,
            "caption": caption,
        }
    if action == "show_flow":
        return {
            "action": "show_flow",
            "from": step.from_id,
            "to": step.to_id,
            "caption": caption,
        }
    if action == "highlight_component":
        return {
            "action": "highlight_component",
            "component": step.component or step.node,
            "caption": caption,
        }

    allowed = _PASSTHROUGH_KEYS.get(action)
    if allowed is None:
        return None
    raw = step.model_dump(by_alias=True, exclude_none=True)
    return {"action": action, **{key: raw[key] for key in allowed if key in raw}}