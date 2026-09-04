"""Tree visualization agent — recursive Reingold–Tilford-style coordinates."""

from __future__ import annotations

from typing import Any

from tree_extractor import extract_tree, walk_inorder, walk_postorder, walk_preorder

from visualization.schema import DslStep, VisualizationDocument

DEFAULT_TREE: dict[str, Any] = {
    "value": 10,
    "left": {
        "value": 5,
        "left": {"value": 3},
        "right": {"value": 7},
    },
    "right": {"value": 20},
}


def _resolve_tree(ir: dict[str, Any]) -> tuple[dict[str, Any], str]:
    real = ir.get("extracted_tree")
    if not isinstance(real, dict):
        real = extract_tree(ir.get("source_code") or "", ir.get("language") or "")
    if isinstance(real, dict) and "value" in real:
        return real, "your tree"
    return DEFAULT_TREE, "illustrative tree"


def plan_tree(ir: dict[str, Any]) -> VisualizationDocument:
    algorithm = ir.get("algorithm") or "inorder_traversal"
    tree, source_label = _resolve_tree(ir)
    is_real = source_label == "your tree"

    if algorithm == "preorder_traversal":
        title = "Preorder Traversal"
        path = (
            [(v, f"Visit {v}") for v in walk_preorder(tree)]
            if is_real
            else [
                (10, "Visit root first"),
                (5, "Left"),
                (3, "Leftmost"),
                (7, "Right of 5"),
                (20, "Right"),
            ]
        )
    elif algorithm == "postorder_traversal":
        title = "Postorder Traversal"
        path = (
            [(v, f"Visit {v}") for v in walk_postorder(tree)]
            if is_real
            else [
                (3, "Leftmost"),
                (7, "Right of 5"),
                (5, "Left subtree"),
                (20, "Right"),
                (10, "Root last"),
            ]
        )
    else:
        title = "Inorder Traversal"
        algorithm = "inorder_traversal"
        path = (
            [(v, f"Visit {v}") for v in walk_inorder(tree)]
            if is_real
            else [
                (10, "Start at root"),
                (5, "Go left"),
                (3, "Visit 3"),
                (5, "Return to 5"),
                (7, "Visit 7"),
                (10, "Return to root"),
                (20, "Visit 20"),
            ]
        )

    steps = [
        DslStep(action="show_title", text=title),
        DslStep(
            action="show_tree",
            tree=tree,
            caption=f"Binary tree ({source_label}, layout computed, not LLM)",
        ),
    ]
    previous = None
    for node, caption in path:
        if previous is not None and previous != node:
            steps.append(
                DslStep(
                    action="move_pointer",
                    **{"from": previous, "to": node, "caption": caption},
                )
            )
        steps.append(DslStep(action="highlight", node=node, caption=caption))
        steps.append(DslStep(action="visit", node=node, caption=f"Visited {node}"))
        previous = node
    steps.append(DslStep(action="show_caption", text=f"{title} complete"))

    return VisualizationDocument(
        domain="tree",
        type="tree",
        algorithm=algorithm,
        title=title,
        data_structure="binary_tree",
        tree=tree,
        steps=steps,
    )
