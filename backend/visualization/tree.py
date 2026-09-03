"""Tree visualization agent — recursive Reingold–Tilford-style coordinates."""

from __future__ import annotations

from typing import Any

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


def plan_tree(ir: dict[str, Any]) -> VisualizationDocument:
    algorithm = ir.get("algorithm") or "inorder_traversal"
    tree = DEFAULT_TREE
    if algorithm == "preorder_traversal":
        path = [(10, "Visit root first"), (5, "Left"), (3, "Leftmost"), (7, "Right of 5"), (20, "Right")]
        title = "Preorder Traversal"
    elif algorithm == "postorder_traversal":
        path = [(3, "Leftmost"), (7, "Right of 5"), (5, "Left subtree"), (20, "Right"), (10, "Root last")]
        title = "Postorder Traversal"
    else:
        path = [
            (10, "Start at root"),
            (5, "Go left"),
            (3, "Visit 3"),
            (5, "Return to 5"),
            (7, "Visit 7"),
            (10, "Return to root"),
            (20, "Visit 20"),
        ]
        title = "Inorder Traversal"
        algorithm = "inorder_traversal"

    steps = [
        DslStep(action="show_title", text=title),
        DslStep(action="show_tree", tree=tree, caption="Binary tree layout (computed, not LLM)"),
    ]
    previous = None
    for node, caption in path:
        if previous is not None and previous != node:
            steps.append(
                DslStep(action="move_pointer", **{"from": previous, "to": node, "caption": caption})
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
