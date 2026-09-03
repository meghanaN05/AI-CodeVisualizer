"""Extract the ACTUAL graph (nodes, edges, weights) from user source code.

The parsers only capture syntax (function/loop/condition names). To visualize
a user's real graph we must recover the concrete data they wrote: the nodes,
the edges, and the edge weights. This module does a best-effort extraction
across the supported languages using ASTs (Python) and lightweight textual
parsing (C++/Java/JS), so the planner is fed the real input instead of a
fabricated example.

Extraction strategies, in priority order:
  1. A Python adjacency-dict literal:  graph = {"A": [("B", 4), ...], ...}
  2. A Python edge-list literal:        edges = [("A", "B", 4), ...]
  3. A C++/Java/JS adjacency or edge vector literal.
  4. Imperative push_back(edge) / addEdge(...) statements (best-effort).

Returns a dict {nodes, edges, source} where:
  nodes: list[str]
  edges: list[(str, str, weight)]  (weight int/float/str)
  source: str | None  (the source node id, if determinable)
or None when nothing concrete could be extracted.
"""

from __future__ import annotations

import ast
import re
from typing import Any

# Keywords that indicate the variable holds a graph / edge list.
_ADJACENCY_NAMES = ("graph", "adj", "adjacency", "g")
_EDGE_NAMES = ("edges", "edge_list", "edge", "route", "connections")


def extract_graph(code: str, language: str) -> dict[str, Any] | None:
    """Return the user's real graph, or None if it cannot be recovered."""
    lang = (language or "").strip().lower()

    if lang in {"python", "py"}:
        return _extract_python(code)
    if lang in {"cpp", "c++", "c"}:
        return _extract_cpp(code)
    if lang == "java":
        return _extract_java(code)
    if lang in {"javascript", "js"}:
        return _extract_javascript(code)
    return None


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
def _extract_python(code: str) -> dict[str, Any] | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    assignments: list[tuple[str, ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, node.value))

    # 1) adjacency-dict literal
    for name, value in assignments:
        if name.lower() in _ADJACENCY_NAMES and isinstance(value, ast.Dict):
            graph = _adjacency_dict(value)
            if graph:
                return graph

    # 2) edge-list literal (flat list of tuples)
    for name, value in assignments:
        if name.lower() in _EDGE_NAMES and isinstance(value, ast.List):
            edges = _edge_list(value)
            if edges:
                nodes = sorted({str(u) for u, v, _w in edges})
                return {
                    "nodes": nodes,
                    "edges": edges,
                    "source": nodes[0] if nodes else None,
                }

    return None


def _adjacency_dict(node: ast.Dict) -> dict[str, Any] | None:
    """Parse {'A': [('B', 4), ('C', 2)], ...} into {nodes, edges, source}."""
    nodes: list[str] = []
    edges: list[tuple[str, str, Any]] = []
    seen_nodes: set[str] = set()

    for key, value in zip(node.keys, node.values):
        try:
            label = str(ast.literal_eval(key))
        except (ValueError, TypeError):
            continue
        if label not in seen_nodes:
            seen_nodes.add(label)
            nodes.append(label)

        neighbors = value.elts if isinstance(value, ast.List) else []
        for element in neighbors:
            # Weighted adjacency: ("B", 4)
            if isinstance(element, ast.Tuple) and len(element.elts) >= 1:
                try:
                    target = str(ast.literal_eval(element.elts[0]))
                except (ValueError, TypeError):
                    continue
                weight: Any = 1
                if len(element.elts) >= 2:
                    weight = _to_weight(ast.literal_eval(element.elts[1]))
            # Unweighted adjacency: "B"
            else:
                try:
                    target = str(ast.literal_eval(element))
                except (ValueError, TypeError):
                    continue
                weight = 1
            if target not in seen_nodes:
                seen_nodes.add(target)
                nodes.append(target)
            edges.append((label, target, weight))

    if not nodes and not edges:
        return None
    if not edges:
        # Isolated nodes only — still usable.
        return {"nodes": nodes, "edges": edges, "source": nodes[0] if nodes else None}
    # Prefer the first node that has outgoing edges as the source.
    out_nodes = {u for u, _v, _w in edges}
    source = nodes[0] if nodes[0] in out_nodes else (next(iter(out_nodes), None))
    return {"nodes": nodes, "edges": edges, "source": source}


def _edge_list(node: ast.List) -> list[tuple[str, str, Any]]:
    edges: list[tuple[str, str, Any]] = []
    for element in node.elts:
        if not isinstance(element, ast.Tuple) or len(element.elts) < 2:
            continue
        try:
            u = str(ast.literal_eval(element.elts[0]))
            v = str(ast.literal_eval(element.elts[1]))
        except (ValueError, TypeError):
            continue
        weight: Any = 1
        if len(element.elts) >= 3:
            weight = _to_weight(ast.literal_eval(element.elts[2]))
        edges.append((u, v, weight))
    return edges


def _to_weight(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value


# --------------------------------------------------------------------------- #
# C++ / Java / JavaScript (best-effort)
# --------------------------------------------------------------------------- #
def _extract_cpp(code: str) -> dict[str, Any] | None:
    return _extract_brace_or_list_adjacency(code) or _extract_imperative(code)


def _extract_java(code: str) -> dict[str, Any] | None:
    return _extract_brace_or_list_adjacency(code) or _extract_imperative(code)


def _extract_javascript(code: str) -> dict[str, Any] | None:
    return _extract_brace_or_list_adjacency(code) or _extract_imperative(code)


def _extract_brace_or_list_adjacency(code: str) -> dict[str, Any] | None:
    """Parse inline adjacency-list literals such as:

    C++: vector<vector<int>> graph = {{1, 2}, {0, 3}, {0}, {1}};
    Java: int[][] graph = {{1, 2}, {0, 3}, {0}, {1}};
    JS:   const graph = [[1, 2], [0, 3], [0], [1]];

    Interprets the outer index as the node id and inner values as neighbors.
    If the literal is symmetric, duplicate undirected edges are collapsed.
    """
    match = re.search(
        r"\b(?:graph|adj|adjacency)\w*\b\s*=\s*(\{\s*\{|\[\s*\[)",
        code,
        re.IGNORECASE,
    )
    if not match:
        return None

    start = match.start(1)
    literal = _extract_nested_literal(code, start)
    if not literal:
        return None

    rows = _parse_nested_numeric_rows(literal)
    if rows is None:
        return None

    nodes = [str(i) for i in range(len(rows))]
    raw_edges: list[tuple[str, str, Any]] = []
    for u, neighbors in enumerate(rows):
        for v in neighbors:
            raw_edges.append((str(u), str(v), 1))

    edges = _dedupe_undirected_if_symmetric(raw_edges)
    if not nodes and not edges:
        return None

    out_nodes = {u for u, _v, _w in edges}
    source = (
        nodes[0]
        if nodes and nodes[0] in out_nodes
        else (next(iter(out_nodes), nodes[0] if nodes else None))
    )
    return {"nodes": nodes, "edges": edges, "source": source}


def _extract_imperative(code: str) -> dict[str, Any] | None:
    """Parse addEdge(u,v,w) / g[u].push_back({v,w}) style construction.

    This is inherently lossy; we accept imperfect recovery rather than
    substituting a fabricated graph.
    """
    edges: list[tuple[str, str, Any]] = []
    nodes: set[str] = set()

    # addEdge(u, v, w) or addEdge(u, v) — with or without weights
    add_edge_re = re.compile(
        r"\b(?:add_?[Ee]dge|insertEdge|connect|edge)\s*\(\s*"
        r"([\"']?[A-Za-z_][\w-]*[\"']?)\s*,\s*"
        r'(["\']?[A-Za-z_][\w-]*["\']?)\s*'
        r"(?:,\s*([0-9.]+))?\s*\)"
    )
    for match in add_edge_re.finditer(code):
        u = match.group(1).strip("\"'")
        v = match.group(2).strip("\"'")
        weight: Any = match.group(3) if match.group(3) is not None else 1
        weight = _to_weight(weight)
        nodes.add(u)
        nodes.add(v)
        edges.append((u, v, weight))

    # g[u] = [(v, w), ...] adjacency literal (common in JS)
    adj_re = re.compile(
        r'\b([A-Za-z_]\w*)\s*\[\s*(["\']?[A-Za-z_]\w*["\']?)\s*\]\s*=\s*\[(.*?)\]',
        re.DOTALL,
    )
    for match in adj_re.finditer(code):
        u = match.group(2).strip("\"'")
        nodes.add(u)
        body = match.group(3)
        for inner in re.finditer(
            r"\(\s*([\"']?[A-Za-z_]\w*[\"']?)\s*,\s*([0-9.]+)\s*\)", body
        ):
            v = inner.group(1).strip("\"'")
            w = _to_weight(inner.group(2))
            nodes.add(v)
            edges.append((u, v, w))

    if not edges:
        return None

    node_list = sorted(nodes)
    out_nodes = {u for u, _v, _w in edges}
    source = (
        node_list[0] if node_list[0] in out_nodes else (next(iter(out_nodes), None))
    )
    return {"nodes": node_list, "edges": edges, "source": source}


def _extract_nested_literal(code: str, start: int) -> str | None:
    opening = code[start]
    closing = "}" if opening == "{" else "]"
    depth = 0

    for index in range(start, len(code)):
        char = code[index]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return code[start : index + 1]
    return None


def _parse_nested_numeric_rows(literal: str) -> list[list[int]] | None:
    translated = literal.replace("{", "[").replace("}", "]")
    try:
        value = ast.literal_eval(translated)
    except (SyntaxError, ValueError):
        return None

    if not isinstance(value, list):
        return None

    rows: list[list[int]] = []
    for row in value:
        if not isinstance(row, list):
            return None
        parsed_row: list[int] = []
        for item in row:
            if isinstance(item, bool):
                return None
            if isinstance(item, int):
                parsed_row.append(item)
            elif isinstance(item, float) and item.is_integer():
                parsed_row.append(int(item))
            else:
                return None
        rows.append(parsed_row)
    return rows


def _dedupe_undirected_if_symmetric(
    edges: list[tuple[str, str, Any]],
) -> list[tuple[str, str, Any]]:
    if not edges:
        return edges

    edge_pairs = {(u, v) for u, v, _w in edges}
    is_symmetric = all((v, u) in edge_pairs for u, v, _w in edges)
    if not is_symmetric:
        return edges

    deduped: list[tuple[str, str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for u, v, w in edges:
        key = tuple(sorted((u, v)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((key[0], key[1], w))
    return deduped
