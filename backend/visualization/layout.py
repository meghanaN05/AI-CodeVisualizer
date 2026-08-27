"""Deterministic layout engine with collision detection.

Separates "what to show" (DSL) from "where to put it" (layout).

The LLM/planner decides WHAT nodes/edges/steps exist. This module decides
WHERE each node goes so that objects never overlap, and produces coordinates
the renderer can use directly.

Graphs use NetworkX layouts; generic graphs fall back to a deterministic
circular placement. After layout, a collision check runs and overlapping
nodes are pushed apart (reflow).
"""

from __future__ import annotations

import math
from typing import Any

# Manim canvas is roughly x in [-7, 7], y in [-4, 4]. Keep a margin so
# nodes near the edge never get clipped.
CANVAS_WIDTH = 14.0
CANVAS_HEIGHT = 8.0
MARGIN = 2.0

# Each node is drawn as a circle with this radius in coordinate units.
NODE_RADIUS = 0.5
MIN_NODE_SEPARATION = NODE_RADIUS + 0.25


def compute_graph_layout(
    nodes: list[str],
    edges: list[tuple[str, str, Any]],
    scale: float = 1.0,
) -> dict[str, tuple[float, float]]:
    """Produce collision-free {node_id: (x, y)} coordinates.

    Uses NetworkX spring layout when available and there are enough nodes,
    otherwise a deterministic circular layout. Result is scaled to the Manim
    canvas and then collision-checked / reflowed.
    """
    nodes = list(dict.fromkeys(str(n) for n in nodes))

    if len(nodes) <= 1:
        return {nodes[0]: (0.0, 0.0)} if nodes else {}

    try:
        positions = _networkx_layout(nodes, edges)
    except Exception:
        positions = _circular_layout(nodes)

    positions = _scale_to_canvas(positions, len(nodes))
    positions = _reflow(positions)
    if scale != 1.0:
        positions = {n: (x * scale, y * scale) for n, (x, y) in positions.items()}
    return positions


def check_overlaps(
    positions: dict[str, tuple[float, float]],
    min_separation: float = MIN_NODE_SEPARATION,
) -> list[tuple[str, str, float]]:
    """Return [(a, b, distance)] for every pair closer than min_separation."""
    items = list(positions.items())
    overlaps: list[tuple[str, str, float]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            name_a, (ax, ay) = items[i]
            name_b, (bx, by) = items[j]
            dist = math.hypot(ax - bx, ay - by)
            if dist < min_separation:
                overlaps.append((name_a, name_b, dist))
    return overlaps


def reflow_layout(
    positions: dict[str, tuple[float, float]],
    min_separation: float = MIN_NODE_SEPARATION,
    max_iterations: int = 100,
) -> dict[str, tuple[float, float]]:
    """Iteratively push apart nodes that are too close to one another."""
    positions = {k: list(v) for k, v in positions.items()}
    names = list(positions)

    for _ in range(max_iterations):
        moved = False
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                ax, ay = positions[a]
                bx, by = positions[b]
                dx, dy = bx - ax, by - ay
                dist = math.hypot(dx, dy)
                if dist == 0:
                    dx, dy, dist = 1.0, 0.0, 1.0
                if dist < min_separation:
                    push = (min_separation - dist) / 2.0
                    ux, uy = dx / dist, dy / dist
                    positions[a][0] -= ux * push
                    positions[a][1] -= uy * push
                    positions[b][0] += ux * push
                    positions[b][1] += uy * push
                    moved = True
        if not moved:
            break

    return {k: (v[0], v[1]) for k, v in positions.items()}


def _networkx_layout(
    nodes: list[str],
    edges: list[tuple[str, str, Any]],
) -> dict[str, tuple[float, float]]:
    import networkx as nx

    seed = 42
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    for source, target, _weight in edges:
        if str(source) in set(nodes) and str(target) in set(nodes):
            graph.add_edge(str(source), str(target))

    if len(nodes) == 2:
        return {nodes[0]: (-1.0, 0.0), nodes[1]: (1.0, 0.0)}

    raw = nx.spring_layout(graph, seed=seed, k=1.6)
    return {str(name): (float(pos[0]), float(pos[1])) for name, pos in raw.items()}


def _circular_layout(nodes: list[str]) -> dict[str, tuple[float, float]]:
    radius = 1.0
    n = len(nodes)
    return {
        name: (
            radius * math.cos(2 * math.pi * i / n),
            radius * math.sin(2 * math.pi * i / n),
        )
        for i, name in enumerate(nodes)
    }


def _scale_to_canvas(
    positions: dict[str, tuple[float, float]],
    count: int,
) -> dict[str, tuple[float, float]]:
    if not positions:
        return positions
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y

    avail_w = CANVAS_WIDTH - 2 * MARGIN
    avail_h = CANVAS_HEIGHT - 2 * MARGIN

    # More nodes need more room: shrink effective area a bit for large graphs.
    density_factor = 1.0 if count <= 8 else 0.85
    avail_w *= density_factor
    avail_h *= density_factor

    def _map(value: float, lo: float, hi: float, target_lo: float, target_hi: float) -> float:
        if hi - lo < 1e-9:
            return (target_lo + target_hi) / 2.0
        return target_lo + (value - lo) * (target_hi - target_lo) / (hi - lo)

    scaled: dict[str, tuple[float, float]] = {}
    for name, (x, y) in positions.items():
        sx = _map(x, min_x, max_x, -avail_w / 2, avail_w / 2)
        sy = _map(y, min_y, max_y, -avail_h / 2, avail_h / 2)
        scaled[name] = (sx, sy)
    return scaled


def _reflow(
    positions: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    positions = reflow_layout(positions)
    overlaps = check_overlaps(positions)
    if not overlaps:
        return positions

    # Stretch the whole graph if a reflow pass alone could not separate nodes.
    if overlaps:
        positions = _spread(positions)
        positions = reflow_layout(positions)
    return positions


def _spread(
    positions: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Scale coordinates outward from the centroid to increase spacing."""
    if not positions:
        return positions
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    span = max((max(xs) - min(xs)), (max(ys) - min(ys)), 1e-9)
    factor = 1.0 + max(0.0, (CANVAS_WIDTH - 2 * MARGIN) / 2 - span) / span
    factor = min(factor, 2.5)

    return {
        name: (cx + (x - cx) * factor, cy + (y - cy) * factor)
        for name, (x, y) in positions.items()
    }
