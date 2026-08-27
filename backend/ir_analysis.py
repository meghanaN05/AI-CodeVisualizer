"""Language-agnostic IR enrichment — detects DSA concepts from parsed code."""

from __future__ import annotations

import re
from typing import Any

# --- Pattern tables (language-agnostic) ---

HASH_MAP_PATTERNS = [
    r"\bunordered_map\b",
    r"\bhash_map\b",
    r"\bHashMap\b",
    r"\bHashtable\b",
    r"\bHashTable\b",
    r"\bdict\b",
    r"\bDictionary\b",
    r"\bMap\s*<",
    r"\bmap\s*<",
    r"\bObject\b.*\[",
    r"\bnew\s+Map\s*\(",
]

HEAP_PATTERNS = [
    r"\bpriority_queue\b",
    r"\bPriorityQueue\b",
    r"\bheapq\b",
    r"\bHeap\b",
    r"\bMinHeap\b",
    r"\bMaxHeap\b",
]

SET_PATTERNS = [
    r"\bunordered_set\b",
    r"\bHashSet\b",
    r"\bset\s*<",
    r"\bSet\s*<",
    r"\bnew\s+Set\s*\(",
]

STACK_PATTERNS = [
    r"\bstack\s*<",
    r"\bStack\b",
    r"\bpush\s*\(",
    r"\bpop\s*\(",
]

QUEUE_PATTERNS = [
    r"\bqueue\s*<",
    r"\bQueue\b",
    r"\bdeque\b",
    r"\bDeque\b",
]

GRAPH_PATTERNS = [
    r"\badjacency\b",
    r"\bgraph\b",
    r"\bfollows?\b",
    r"\bneighbors?\b",
    r"\bvertices\b",
    r"\bedges?\b",
    r"\bvisited\b",
    r"\bDFS\b",
    r"\bBFS\b",
]

TREE_PATTERNS = [
    r"\bNode\s*\*",
    r"\btree\b",
    r"\bleft\b.*\bright\b",
    r"\bBinaryTree\b",
    r"\bTreeNode\b",
]

LINKED_LIST_PATTERNS = [
    r"\bListNode\b",
    r"\bnext\b",
    r"\bprev\b",
    r"\blinked\s*list\b",
]

TRIE_PATTERNS = [r"\btrie\b", r"\bTrie\b", r"\bprefix\b"]

UNION_FIND_PATTERNS = [r"\bunion\b.*\bfind\b", r"\bUnionFind\b", r"\bdisjoint\b"]

DESIGN_PATTERNS: dict[str, list[str]] = {
    "twitter_design": [
        r"\bTwitter\b",
        r"\bpostTweet\b",
        r"\bgetNewsFeed\b",
        r"\bfollow\b",
        r"\bunfollow\b",
    ],
    "lru_cache": [r"\bLRU\b", r"\bLRUCache\b", r"\blru\b"],
    "lfu_cache": [r"\bLFU\b", r"\bLFUCache\b"],
    "min_stack": [r"\bMinStack\b", r"\bminStack\b"],
    "design_twitter": [r"\bDesignTwitter\b"],
    "hash_map_design": [r"\bMyHashMap\b", r"\bHashMap\b.*class"],
    "heap_design": [r"\bKthLargest\b", r"\bMedianFinder\b"],
    "graph_design": [r"\bGraph\b", r"\bCourseSchedule\b", r"\bWordLadder\b"],
    "tree_design": [r"\bCodec\b", r"\bSerialize\b", r"\bDeserialize\b"],
    "union_find": [r"\bUnionFind\b", r"\bnumIslands\b", r"\bRedundantConnection\b"],
    "trie_design": [r"\bTrie\b", r"\bWordSearch\b", r"\bimplementTrie\b"],
    "dynamic_programming": [
        r"\bdp\s*\[",
        r"\bmemo\s*\[",
        r"\bcache\s*\[",
        r"\bdynamic\s+programming\b",
    ],
    "backtracking": [r"\bbacktrack\b", r"\bpermutations?\b", r"\bcombinations?\b"],
    "sliding_window": [r"\bsliding\s+window\b", r"\bwindowStart\b", r"\bwindowEnd\b"],
    "two_pointers": [r"\btwo\s+pointers\b", r"\bleft\s*=\s*0.*right"],
    "dijkstra": [
        r"\bDijkstra\b",
        r"\bdijkstra\b",
        r"\bshortest\s*path\b",
        r"\bpriority_queue\b.*\bdistance\b",
        r"\bdist\[\s*\]",
    ],
}


def enrich_ir(ir: dict[str, Any], code: str, language: str) -> dict[str, Any]:
    """Augment a partial IR with cross-language DSA analysis."""
    ir.setdefault("language", language)
    ir.setdefault("source_code", code)
    ir.setdefault("functions", [])
    ir.setdefault("classes", [])
    ir.setdefault("methods", [])
    ir.setdefault("variables", [])
    ir.setdefault("conditions", [])
    ir.setdefault("calls", [])
    ir.setdefault("loops", [])
    ir.setdefault("arrays", [])
    ir.setdefault("data_structures", [])
    ir.setdefault("operations", [])

    detected = _detect_all_structures(code)
    existing = set(ir.get("data_structures") or [])
    merged_structures = list(existing)
    for item in detected:
        if item not in merged_structures:
            merged_structures.append(item)
    ir["data_structures"] = merged_structures

    ir["concepts"] = _detect_concepts(code, ir)
    ir["algorithm"] = ir.get("algorithm") or _detect_algorithm(code, ir)
    ir["methods"] = _collect_methods(ir)
    ir["operations"] = _derive_operations(ir)
    return ir


def _detect_all_structures(code: str) -> list[str]:
    structures: list[str] = []
    checks = [
        (HASH_MAP_PATTERNS, "hash_map"),
        (HEAP_PATTERNS, "heap"),
        (SET_PATTERNS, "set"),
        (STACK_PATTERNS, "stack"),
        (QUEUE_PATTERNS, "queue"),
        (GRAPH_PATTERNS, "graph"),
        (TREE_PATTERNS, "binary_tree"),
        (LINKED_LIST_PATTERNS, "linked_list"),
        (TRIE_PATTERNS, "trie"),
        (UNION_FIND_PATTERNS, "union_find"),
    ]
    for patterns, name in checks:
        if any(re.search(p, code, re.IGNORECASE) for p in patterns):
            structures.append(name)

    # A "bare []" is ambiguous (e.g. empty adjacency lists inside a graph
    # literal), so only treat clearly-assigned list/vector values as arrays.
    if re.search(r"\bvector\s*<|\bArrayList\b|\blist\s*\[|\b\w+\s*=\s*\[", code):
        if "array" not in structures:
            structures.append("array")

    return structures


def _detect_concepts(code: str, ir: dict[str, Any]) -> list[str]:
    concepts: list[str] = []
    for concept, patterns in DESIGN_PATTERNS.items():
        if sum(1 for p in patterns if re.search(p, code, re.IGNORECASE)) >= 1:
            if concept == "twitter_design":
                matches = sum(
                    1
                    for p in patterns
                    if re.search(p, code, re.IGNORECASE)
                )
                if matches >= 2:
                    concepts.append(concept)
            elif concept == "design_twitter":
                if "twitter_design" not in concepts:
                    concepts.append("twitter_design")
            else:
                concepts.append(concept)

    if any(fn.get("recursive") for fn in ir.get("functions", [])):
        concepts.append("recursion")
    if len(ir.get("loops", [])) >= 2:
        concepts.append("nested_loops")
    if ir.get("classes"):
        concepts.append("object_oriented")

    seen: set[str] = set()
    ordered: list[str] = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def _detect_algorithm(code: str, ir: dict[str, Any]) -> str | None:
    concepts = ir.get("concepts") or []
    if "twitter_design" in concepts:
        return "twitter_design"
    if "lru_cache" in concepts:
        return "lru_cache"
    if "trie_design" in concepts or "trie" in (ir.get("data_structures") or []):
        return "trie"
    if "union_find" in concepts:
        return "union_find"
    if "dynamic_programming" in concepts:
        return "dynamic_programming"
    if "dijkstra" in concepts:
        return "dijkstra"
    if "backtracking" in concepts:
        return "backtracking"
    if "heap" in (ir.get("data_structures") or []) and "hash_map" in (
        ir.get("data_structures") or []
    ):
        return "heap_hashmap_composite"

    method_names = {m.lower() for m in _collect_method_names(ir)}
    if {"posttweet", "getnewsfeed", "follow"} & method_names:
        return "twitter_design"

    return ir.get("algorithm")


def _collect_methods(ir: dict[str, Any]) -> list[dict[str, Any]]:
    methods: list[dict[str, Any]] = []
    for cls in ir.get("classes") or []:
        for method in cls.get("methods") or []:
            entry = dict(method)
            entry["class"] = cls.get("name")
            methods.append(entry)
    for fn in ir.get("functions") or []:
        if not any(m.get("name") == fn.get("name") for m in methods):
            methods.append(
                {
                    "name": fn.get("name"),
                    "class": None,
                    "return_type": fn.get("return_type"),
                    "parameters": fn.get("parameters", []),
                    "recursive": fn.get("recursive", False),
                }
            )
    return methods


def _collect_method_names(ir: dict[str, Any]) -> list[str]:
    return [m.get("name", "") for m in _collect_methods(ir) if m.get("name")]


def _derive_operations(ir: dict[str, Any]) -> list[str]:
    operations = list(ir.get("operations") or [])

    for cls in ir.get("classes") or []:
        operations.append(f"class {cls.get('name')} with {len(cls.get('methods', []))} methods")
        for member in cls.get("members") or []:
            operations.append(f"member: {member.get('name')} ({member.get('type', 'unknown')})")

    for method in _collect_methods(ir):
        params = ", ".join(
            f"{p.get('type', 'any')} {p.get('name', '')}".strip()
            for p in method.get("parameters") or []
        )
        owner = method.get("class") or "global"
        operations.append(f"{owner}.{method.get('name')}({params})")

    structures = ir.get("data_structures") or []
    if structures:
        operations.append("data structures: " + ", ".join(structures))

    concepts = ir.get("concepts") or []
    if concepts:
        operations.append("concepts: " + ", ".join(concepts))

    algorithm = ir.get("algorithm")
    if algorithm:
        operations.append(f"algorithm: {algorithm}")

    # Deduplicate preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for op in operations:
        if op not in seen:
            seen.add(op)
            ordered.append(op)
    return ordered
