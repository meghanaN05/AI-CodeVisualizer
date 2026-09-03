"""Classify input as code, graph problem, tree problem, or system design."""

from __future__ import annotations

import re
from typing import Any, Literal

Domain = Literal["graph", "tree", "array", "system_design", "generic"]

SYSTEM_DESIGN_HINTS = (
    r"\b(system\s*design|architecture|microservice|load\s*balancer|"
    r"api\s*gateway|message\s*queue|kafka|cdn|shard|replica|"
    r"fanout|timeline|news\s*feed)\b"
)
TWITTER_HINTS = r"\b(Twitter|postTweet|getNewsFeed)\b"
GRAPH_ALGO_HINTS = r"\b(dijkstra|bellman|floyd|prim|kruskal|bfs|dfs|shortest\s*path)\b"
TREE_HINTS = r"\b(inorder|preorder|postorder|bst|avl|TreeNode|binary\s*tree)\b"
ARRAY_HINTS = r"\b(sort|binary\s*search|arr\s*\[|vector\s*<)\b"


def classify(code: str, language: str, ir: dict[str, Any] | None = None) -> dict[str, Any]:
    text = code or ""
    lang = (language or "").strip().lower()
    algorithm = (ir or {}).get("algorithm")
    structures = (ir or {}).get("data_structures") or []
    concepts = (ir or {}).get("concepts") or []

    if lang in {"design", "system", "architecture", "text"}:
        domain: Domain = "system_design"
    elif algorithm == "twitter_design" or "twitter_design" in concepts:
        domain = "system_design"
    elif re.search(TWITTER_HINTS, text) and re.search(SYSTEM_DESIGN_HINTS, text, re.I):
        domain = "system_design"
    elif re.search(SYSTEM_DESIGN_HINTS, text, re.I) and not _looks_like_source(text, lang):
        domain = "system_design"
    elif algorithm in {"dijkstra", "bfs", "dfs"} or "graph" in structures:
        domain = "graph"
    elif re.search(GRAPH_ALGO_HINTS, text, re.I):
        domain = "graph"
    elif algorithm and "traversal" in str(algorithm):
        domain = "tree"
    elif "binary_tree" in structures or re.search(TREE_HINTS, text, re.I):
        domain = "tree"
    elif algorithm in {"bubble_sort", "binary_search", "array_processing"} or "array" in structures:
        domain = "array"
    elif re.search(ARRAY_HINTS, text, re.I):
        domain = "array"
    else:
        domain = "generic"

    return {
        "domain": domain,
        "algorithm": algorithm,
        "language": lang,
        "is_source_code": _looks_like_source(text, lang),
    }


def _looks_like_source(text: str, language: str) -> bool:
    if language in {"design", "system", "architecture"}:
        return False
    return bool(
        re.search(
            r"\b(class|def |void |int |function |public |#include|=>|fn )\b",
            text,
        )
    )
