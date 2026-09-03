"""Validate Visualization DSL before layout and render."""

from __future__ import annotations

from visualization.schema import ALLOWED_ACTIONS, VisualizationDocument


class DslValidationError(ValueError):
    pass


def validate_document(doc: VisualizationDocument) -> VisualizationDocument:
    unknown = []
    for step in list(doc.steps) + [s for ch in doc.chapters for s in ch.steps]:
        if step.action not in ALLOWED_ACTIONS:
            unknown.append(step.action)
    if unknown:
        raise DslValidationError(f"Unsupported DSL actions: {sorted(set(unknown))}")

    if doc.type == "graph" and not doc.nodes:
        raise DslValidationError("Graph visualization requires nodes")
    if doc.type == "architecture" and not doc.components:
        raise DslValidationError("Architecture visualization requires components")
    if doc.type == "tree" and not doc.tree:
        raise DslValidationError("Tree visualization requires a tree")
    return doc
