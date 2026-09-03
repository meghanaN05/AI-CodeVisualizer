"""Graph visualization agent — Dijkstra, BFS, DFS as Visualization DSL."""

from __future__ import annotations

from typing import Any

from graph_extractor import extract_graph
from visualization.schema import (
    Chapter,
    DslEdge,
    DslNode,
    DslStep,
    VisualizationDocument,
)

DEFAULT_GRAPH = {
    "nodes": ["A", "B", "C", "D", "E"],
    "edges": [
        ("A", "B", 4),
        ("A", "C", 2),
        ("B", "C", 1),
        ("B", "D", 5),
        ("C", "D", 8),
        ("C", "E", 10),
        ("D", "E", 2),
        ("B", "E", 6),
    ],
    "source": "A",
}


def plan_graph(ir: dict[str, Any]) -> VisualizationDocument:
    algorithm = ir.get("algorithm") or "bfs"
    if algorithm == "dijkstra":
        return plan_dijkstra(ir)
    kind = "BFS" if algorithm != "dfs" else "DFS"
    return plan_traversal(ir, kind)


def plan_dijkstra(ir: dict[str, Any]) -> VisualizationDocument:
    node_ids, weighted_edges, source, source_label = _resolve_graph(ir)
    order, dist_ready, prev = _run_dijkstra(node_ids, weighted_edges, source)

    nodes = [DslNode(id=n, label=n) for n in node_ids]
    edges = [
        DslEdge(**{"from": u, "to": v, "weight": w}) for u, v, w in weighted_edges
    ]

    steps: list[DslStep] = [
        DslStep(action="show_title", text="Dijkstra's Shortest Path"),
        DslStep(
            action="show_weighted_graph",
            caption=f"Weighted {source_label} — shortest paths from {source}",
        ),
        DslStep(
            action="show_variables",
            variables={n: "∞" for n in node_ids},
            caption=f"Initialize dist[{source}]=0, others ∞",
        ),
    ]

    working = {source: 0}
    for node in order:
        steps.append(
            DslStep(
                action="visit",
                node=node,
                caption=f"Settle {node} (dist = {working.get(node, '∞')})",
            )
        )
        for u, v, w in weighted_edges:
            if u != node and v != node:
                continue
            neighbor = v if u == node else u
            base = working.get(node)
            if base is None:
                continue
            new_dist = base + int(w)
            old = working.get(neighbor)
            if old is None or new_dist < old:
                working[neighbor] = new_dist
                steps.append(
                    DslStep(
                        action="relax",
                        **{"from": u, "to": v, "weight": w},
                        caption=f"Relax {u}→{v} ({w}): {neighbor} = {new_dist}",
                    )
                )
                steps.append(
                    DslStep(
                        action="update_distance",
                        node=neighbor,
                        distances={n: working.get(n, "∞") for n in node_ids},
                        label=str(new_dist),
                        caption=f"dist[{neighbor}] = {new_dist}",
                    )
                )

    target = _farthest(node_ids, working, source)
    path = _reconstruct(prev, source, target)
    steps.append(
        DslStep(
            action="show_shortest_path",
            path=path,
            caption=f"Shortest path {source} → {target}: {path}",
        )
    )
    steps.append(
        DslStep(
            action="show_caption",
            text="Distances: " + ", ".join(f"{n}={working.get(n, '∞')}" for n in node_ids),
        )
    )

    scenes_needed = (ir.get("complexity") or {}).get("scenes_required", 5)
    chapters = _split_chapters(
        [
            ("graph", "The graph", 2),
            ("start", "Start node", 1),
            ("relax", "Relax edges", max(1, len(steps) - 6)),
            ("update", "Update distances", 0),
            ("path", "Shortest path", 2),
        ],
        steps,
        scenes_needed,
    )

    return VisualizationDocument(
        domain="graph",
        type="graph",
        algorithm="dijkstra",
        title="Dijkstra's Algorithm",
        data_structure="graph",
        description="Single-source shortest paths on a weighted graph",
        nodes=nodes,
        edges=edges,
        steps=steps,
        chapters=chapters,
    )


def plan_traversal(ir: dict[str, Any], kind: str) -> VisualizationDocument:
    node_ids, weighted_edges, source, _label = _resolve_graph(ir)
    if not weighted_edges:
        node_ids = ["A", "B", "C", "D"]
        weighted_edges = [("A", "B", 1), ("A", "C", 1), ("B", "D", 1), ("C", "D", 1)]
        source = "A"

    order = _bfs(node_ids, weighted_edges, source) if kind == "BFS" else _dfs(
        node_ids, weighted_edges, source
    )
    steps = [
        DslStep(action="show_title", text=f"Graph {kind}"),
        DslStep(action="show_graph", caption=f"{kind} starting at {source}"),
    ]
    for node in order:
        steps.append(DslStep(action="visit", node=node, caption=f"Visit {node}"))
    steps.append(DslStep(action="show_caption", text=f"{kind} complete"))

    return VisualizationDocument(
        domain="graph",
        type="graph",
        algorithm=kind.lower(),
        title=f"Graph {kind}",
        data_structure="graph",
        nodes=[DslNode(id=n, label=n) for n in node_ids],
        edges=[DslEdge(**{"from": u, "to": v, "weight": w}) for u, v, w in weighted_edges],
        steps=steps,
        chapters=[Chapter(id="main", title=f"Graph {kind}", steps=steps)],
    )


def _resolve_graph(ir: dict[str, Any]) -> tuple[list[str], list[tuple], str, str]:
    real = ir.get("extracted_graph") or extract_graph(
        ir.get("source_code") or "", ir.get("language") or ""
    )
    if real and real.get("edges"):
        nodes = list(real["nodes"])
        edges = list(real["edges"])
        source = real.get("source") or nodes[0]
        return nodes, edges, source, "graph from source"
    return (
        list(DEFAULT_GRAPH["nodes"]),
        list(DEFAULT_GRAPH["edges"]),
        DEFAULT_GRAPH["source"],
        "illustrative graph",
    )


def _run_dijkstra(nodes, edges, source):
    adjacency: dict[str, list[tuple[str, Any]]] = {n: [] for n in nodes}
    for u, v, w in edges:
        adjacency.setdefault(u, []).append((v, w))
        adjacency.setdefault(v, []).append((u, w))

    dist = {n: float("inf") for n in nodes}
    prev: dict[str, str] = {}
    dist[source] = 0
    visited: set[str] = set()
    order: list[str] = []

    for _ in range(len(nodes)):
        candidates = [n for n in nodes if n not in visited]
        if not candidates:
            break
        current = min(candidates, key=lambda n: dist[n])
        if dist[current] == float("inf"):
            break
        visited.add(current)
        order.append(current)
        for neighbor, weight in adjacency.get(current, []):
            candidate = dist[current] + int(weight)
            if candidate < dist[neighbor]:
                dist[neighbor] = candidate
                prev[neighbor] = current

    finite = {n: int(d) for n, d in dist.items() if d != float("inf")}
    return order, finite, prev


def _farthest(nodes, dist, source):
    reachable = [n for n in nodes if n != source and n in dist]
    return max(reachable, key=lambda n: dist[n]) if reachable else source


def _reconstruct(prev, source, target):
    if target == source:
        return [source]
    path: list[str] = []
    current = target
    while current in prev:
        path.append(current)
        current = prev[current]
    path.append(current)
    path.reverse()
    return path if path and path[0] == source else [source, target]


def _bfs(nodes, edges, source):
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for u, v, _w in edges:
        adj.setdefault(u, []).append(v)
        adj.setdefault(v, []).append(u)
    seen = {source}
    queue = [source]
    order = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return order


def _dfs(nodes, edges, source):
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for u, v, _w in edges:
        adj.setdefault(u, []).append(v)
        adj.setdefault(v, []).append(u)
    order: list[str] = []
    seen: set[str] = set()

    def walk(cur: str) -> None:
        seen.add(cur)
        order.append(cur)
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                walk(nxt)

    walk(source)
    return order


def _split_chapters(blueprint, steps, scenes_needed):
    if scenes_needed <= 2 or len(steps) < 8:
        return [Chapter(id="main", title="Visualization", steps=steps)]
    return [
        Chapter(id="graph", title="The graph", steps=steps[:2]),
        Chapter(id="start", title="Start node", steps=steps[2:4]),
        Chapter(id="relax", title="Relax edges", steps=steps[4:-2]),
        Chapter(id="path", title="Shortest path", steps=steps[-2:]),
    ]
