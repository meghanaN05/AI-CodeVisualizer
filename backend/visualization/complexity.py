"""Estimate visualization complexity so large problems become multiple chapters."""

from __future__ import annotations

from typing import Any

from visualization.schema import ComplexityReport


def analyze_complexity(ir: dict[str, Any], extra: dict[str, Any] | None = None) -> ComplexityReport:
    extra = extra or {}
    graph = extra.get("graph") or {}
    nodes = len(graph.get("nodes") or extra.get("nodes") or [])
    edges = len(graph.get("edges") or extra.get("edges") or [])
    methods = len(ir.get("methods") or [])
    classes = len(ir.get("classes") or [])
    loops = len(ir.get("loops") or [])

    score = nodes + edges + methods * 2 + classes * 2 + loops
    if score <= 8:
        level = "low"
        scenes = 2
    elif score <= 20:
        level = "medium"
        scenes = 4
    else:
        level = "high"
        scenes = min(10, 5 + score // 10)

    if ir.get("algorithm") == "twitter_design" or extra.get("domain") == "system_design":
        level = "high" if level != "low" else "medium"
        scenes = max(scenes, 6)

    if ir.get("algorithm") == "dijkstra":
        scenes = max(scenes, 5)

    return ComplexityReport(
        nodes=nodes,
        edges=edges,
        methods=methods,
        classes=classes,
        steps=0,
        scenes_required=scenes,
        complexity=level,  # type: ignore[arg-type]
    )
