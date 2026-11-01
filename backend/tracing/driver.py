"""Synthesize example arguments for snippets that define but never call code.

A pasted snippet is often just a function. To trace it we must call it, so we
pick small example inputs from each parameter's name and type. The chosen
input is recorded on the trace so the video can say it is an example input,
not data the user wrote.

Arrays get two variants: an ascending one (valid for searching) and a
shuffled one. Tracers run the ascending variant first and switch to the
shuffled one when the function mutates the array, since a function that
rearranges its input is better shown on unsorted data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SORTED_ARRAY = [0, 1, 3, 4, 7, 9, 12]
SHUFFLED_ARRAY = [7, 0, 3, 9, 1, 12, 4]
PERMUTATION = [4, 0, 6, 2, 5, 1, 3]

_ARRAY_NAMES = re.compile(
    r"^(arr|array|nums?|numbers|a|b|values?|vals|data|lst|list|items|xs|prices|heights)\d*$",
    re.IGNORECASE,
)
_SEARCH_NAMES = re.compile(r"^(target|key|x|val|value|goal|needle|search)$", re.IGNORECASE)
_SIZE_NAMES = re.compile(r"^(n|m|size|len|length|count|num|steps|amount)$", re.IGNORECASE)
_INDEX_NAMES = re.compile(r"^(lo|low|left|l|start|begin|i)$", re.IGNORECASE)
_END_INDEX_NAMES = re.compile(r"^(hi|high|right|r|end|j)$", re.IGNORECASE)
_STRING_NAMES = re.compile(r"^(s|str|string|text|word|t|pattern|p)\d*$", re.IGNORECASE)
_GRID_NAMES = re.compile(r"^(grid|matrix|board|mat)$", re.IGNORECASE)


@dataclass(frozen=True)
class Structure:
    """An example linked structure for TreeNode / ListNode parameters.
    `values` is LeetCode's notation: level order with None for a missing
    child (trees), or the node values in order (lists). Each tracer builds
    the real nodes with a small helper outside the traced code."""

    kind: str  # "tree" or "list"
    values: tuple

    def __str__(self) -> str:
        shown = ", ".join("null" if v is None else str(v) for v in self.values)
        return f"{self.kind} [{shown}]"


# A balanced BST (so BST problems work too) and a sparser tree that has
# missing children, which exercises the `if not node` branches.
EXAMPLE_TREES = ((4, 2, 6, 1, 3, 5, 7), (5, 3, 8, 1, None, 7))
EXAMPLE_LIST = (1, 2, 3, 4, 5)
_TREE_NAMES = re.compile(r"^(root|tree|t|root1|root2|t1|t2|node)$", re.IGNORECASE)
_LIST_NAMES = re.compile(r"^(head|l1|l2|list1|list2|heada|headb|node)$", re.IGNORECASE)


def structure_kind(param: "Param") -> str | None:
    hint = param.type_hint.lower()
    if "treenode" in hint:
        return "tree"
    if "listnode" in hint:
        return "list"
    if not hint or hint in {"object", "any"}:
        if _TREE_NAMES.match(param.name) and param.name.lower() != "node":
            return "tree"
        if _LIST_NAMES.match(param.name) and param.name.lower() != "node":
            return "list"
    return None


@dataclass
class Param:
    name: str
    type_hint: str = ""


@dataclass
class DriverPlan:
    function: str
    owner_class: str | None
    args: list[tuple[str, Any]] = field(default_factory=list)
    variant: str = "sorted"

    def describe(self) -> str:
        shown = ", ".join(f"{name}={_short(value)}" for name, value in self.args)
        return f"{self.function}({shown})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "class": self.owner_class,
            "args": [
                [name, {value.kind: list(value.values)} if isinstance(value, Structure) else value]
                for name, value in self.args
            ],
            "variant": self.variant,
            "description": f"Example input (not in your snippet): {self.describe()}",
        }


def synthesize_args(params: list[Param], variant: str = "sorted") -> list[tuple[str, Any]] | None:
    """Pick example values for each parameter; None if any can't be guessed."""
    array = list(SORTED_ARRAY if variant == "sorted" else SHUFFLED_ARRAY)
    has_array = any(_is_array_param(p) for p in params)
    args: list[tuple[str, Any]] = []
    for param in params:
        value = _guess(param, array, has_array)
        if value is _UNKNOWN:
            return None
        args.append((param.name, value))
    return args


_UNKNOWN = object()

# Runs longer than this make long videos without showing more of the code,
# so among inputs covering the same lines the shorter run wins.
COMFORTABLE_STEPS = 400


def input_score(trace: dict[str, Any], entry_frames_only: set[str] = frozenset({"<module>", "main"})) -> tuple:
    """How good a traced example input is: runs cleanly, finishes, executes
    as many distinct lines as possible, and is not needlessly long (e.g. a
    2^n subset loop on 7 elements)."""
    steps = trace.get("steps") or []
    covered = len({s["line"] for s in steps if s["func"] not in entry_frames_only})
    return (
        not trace.get("error"),
        not trace.get("truncated"),
        covered,
        -max(0, len(steps) - COMFORTABLE_STEPS),
    )


def candidate_args(params: list[Param], variant: str = "sorted", limit: int = 10) -> list[list[tuple[str, Any]]]:
    """Several plausible argument sets, so the tracer can keep the one that
    exercises the most of the code (e.g. a k for which a match exists)."""
    base = synthesize_args(params, variant)
    if base is None:
        return []
    candidates = [base]
    array = next(
        (v for _n, v in base if isinstance(v, list) and len(v) >= 5 and all(isinstance(x, int) for x in v)),
        None,
    )
    if array is not None:
        # Many functions use the values as indexes (permutations, jumps,
        # next pointers); a permutation of 0..n-1 is valid input for them.
        permutation = list(range(len(array))) if variant == "sorted" else list(PERMUTATION[: len(array)])
        candidates.append([(n, permutation if v is array else v) for n, v in base])
        # A short array keeps exponential / nested-loop code to a watchable length.
        candidates.append([(n, array[:4] if v is array else v) for n, v in base])
        # Boundary values (the array's min and max) matter for guards like
        # `if (min < k) return -1;` that would otherwise skip the rest of the code.
        picks = [array[1], array[len(array) // 2], array[1] + array[2], array[2] + array[3] + array[4],
                 min(array), max(array)]
        for position, (name, value) in enumerate(base):
            tunable = _SEARCH_NAMES.match(name) or name.lower() == "k" or not (
                _SIZE_NAMES.match(name) or _INDEX_NAMES.match(name) or _END_INDEX_NAMES.match(name)
            )
            if not tunable or not isinstance(value, int) or isinstance(value, bool):
                continue
            for pick in picks:
                if pick != value:
                    variant_args = list(base)
                    variant_args[position] = (name, pick)
                    candidates.append(variant_args)
    trees = [v for _n, v in base if isinstance(v, Structure) and v.kind == "tree"]
    for position, (name, value) in enumerate(base):
        if isinstance(value, Structure) and value.kind == "tree":
            for shape in EXAMPLE_TREES[1:]:
                variant_args = list(base)
                variant_args[position] = (name, Structure("tree", shape))
                candidates.append(variant_args)
        elif trees and _SEARCH_NAMES.match(name) and isinstance(value, int):
            # A value already in the tree (search/delete) and one that is not
            # (insert); coverage decides which shows more of the code.
            present = [v for v in trees[0].values if v is not None]
            for pick in (present[len(present) // 2], max(present) + 2):
                variant_args = list(base)
                variant_args[position] = (name, pick)
                candidates.append(variant_args)
    unique: list[list[tuple[str, Any]]] = []
    for args in candidates:
        if args not in unique:
            unique.append(args)
    return unique[:limit]


def _guess(param: Param, array: list[int], has_array: bool) -> Any:
    name = param.name
    hint = param.type_hint.lower().replace(" ", "")
    kind = structure_kind(param)
    if kind == "tree":
        return Structure("tree", EXAMPLE_TREES[0])
    if kind == "list":
        return Structure("list", EXAMPLE_LIST)

    if _GRID_NAMES.match(name) or hint.count("[]") >= 2 or "vector<vector" in hint or "list[list" in hint:
        return [[1, 3, 1], [1, 5, 1], [4, 2, 1]]
    if _is_array_param(param):
        if "str" in hint or "char" in hint:
            return ["b", "d", "a", "c"]
        return array
    if "str" in hint or "char*" in hint or (not hint and _STRING_NAMES.match(name)):
        return "({[]})" if "paren" in name.lower() else "abcab"
    if "bool" in hint:
        return True
    if _SEARCH_NAMES.match(name):
        return array[len(array) // 2 + 1] if has_array else 7
    if _INDEX_NAMES.match(name) and has_array:
        return 0
    if _END_INDEX_NAMES.match(name) and has_array:
        return len(array) - 1
    if _SIZE_NAMES.match(name) or name.lower() == "k":
        return len(array) if has_array and name.lower() in {"n", "size", "len", "length"} else 5
    if not hint or any(t in hint for t in ("int", "long", "float", "double", "number")):
        return 5
    return _UNKNOWN


def _is_array_param(param: Param) -> bool:
    if structure_kind(param):
        return False  # "ListNode" starts with "list" but is not an array
    hint = param.type_hint.lower().replace(" ", "")
    if hint.count("[]") == 1 or hint.startswith(("list[", "list", "vector<", "array", "int*", "number[]")):
        return "list[list" not in hint and "vector<vector" not in hint
    return not hint and bool(_ARRAY_NAMES.match(param.name))


def _short(value: Any) -> str:
    text = repr(value) if isinstance(value, str) else str(value)
    if isinstance(value, Structure):
        return text
    return text if len(text) <= 40 else text[:37] + "..."
