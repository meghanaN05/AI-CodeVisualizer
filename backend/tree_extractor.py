"""Extract the ACTUAL binary tree / BST from user source code.

Mirrors graph_extractor.py's philosophy: recover the concrete node values
and left/right structure the user actually wrote, instead of always
falling back to a fabricated example tree.

Extraction strategies, in priority order:
  1. A literal nested tree object assigned to a tree-ish name:
       Python: tree = {"value": 10, "left": {...}, "right": {...}}
       JS:     const tree = {value: 10, left: {...}, right: {...}}
  2. A flat list of values assigned to a tree-ish variable name, built into
     a tree by:
       a. Level-order construction with None/null gaps (the common
          "LeetCode array representation" of a binary tree), when the list
          contains an explicit null/None entry.
       b. Otherwise, sequential BST insertion (the common textbook pattern
          of inserting values one-by-one into an initially empty BST).

Because "flat list of values" is an easy false-positive trap (plain array
code often uses names like "arr"/"values" too), strategy 2 only runs when
the surrounding code has real textual evidence of tree/BST work (TreeNode,
inorder/preorder/postorder, "binary tree", or left+right+node/tree
mentions together).

Returns a dict {"value": ..., "left": {...}|None, "right": {...}|None} or
None when nothing concrete could be recovered.
"""

from __future__ import annotations

import ast
import re
from typing import Any

_TREE_NAMES = ("tree", "root", "bst")
_VALUES_NAMES = (
    "values",
    "nums",
    "data",
    "arr",
    "array",
    "items",
    "elements",
    "tree_values",
    "node_values",
    "bst_values",
)

_STRONG_TREE_HINTS = [
    r"\bTreeNode\b",
    r"\bBST\b",
    r"\bbinary\s*search\s*tree\b",
    r"\bbinary\s*tree\b",
    r"\binorder\b",
    r"\bpreorder\b",
    r"\bpostorder\b",
    r"\bbuild_?[Tt]ree\b",
]


def extract_tree(code: str, language: str) -> dict[str, Any] | None:
    """Return the user's real binary tree, or None if it cannot be recovered."""
    lang = (language or "").strip().lower()

    if lang in {"python", "py"}:
        nested = _extract_python_nested(code)
        if nested is not None:
            return nested
        values = _extract_python_values(code) if _has_tree_context(code) else None
    elif lang in {"javascript", "js"}:
        nested = _extract_js_nested(code)
        if nested is not None:
            return nested
        values = _extract_generic_values(code) if _has_tree_context(code) else None
    elif lang in {"cpp", "c++", "c", "java"}:
        values = _extract_generic_values(code) if _has_tree_context(code) else None
    else:
        values = None

    if not values:
        return None
    return _build_tree_from_values(values)


def _has_tree_context(code: str) -> bool:
    if any(re.search(p, code, re.IGNORECASE) for p in _STRONG_TREE_HINTS):
        return True
    has_left_right = re.search(r"\bleft\b", code, re.IGNORECASE) and re.search(
        r"\bright\b", code, re.IGNORECASE
    )
    has_node_hint = re.search(r"\bnode\b", code, re.IGNORECASE) or re.search(
        r"\btree\b", code, re.IGNORECASE
    )
    return bool(has_left_right and has_node_hint)


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
def _extract_python_nested(code: str) -> dict[str, Any] | None:
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None

    for node in ast.walk(parsed):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.lower() in _TREE_NAMES:
                if isinstance(node.value, ast.Dict):
                    result = _dict_literal_to_tree(node.value)
                    if result:
                        return result
    return None


def _dict_literal_to_tree(node: ast.Dict) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    has_value = False
    for key, value in zip(node.keys, node.values):
        if key is None:
            continue
        try:
            key_name = str(ast.literal_eval(key)).lower()
        except (ValueError, TypeError):
            continue

        if key_name in ("value", "val", "data"):
            try:
                result["value"] = ast.literal_eval(value)
                has_value = True
            except (ValueError, TypeError):
                continue
        elif key_name == "left":
            if isinstance(value, ast.Dict):
                result["left"] = _dict_literal_to_tree(value)
            elif _is_none_literal(value):
                result["left"] = None
        elif key_name == "right":
            if isinstance(value, ast.Dict):
                result["right"] = _dict_literal_to_tree(value)
            elif _is_none_literal(value):
                result["right"] = None

    return result if has_value else None


def _is_none_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _extract_python_values(code: str) -> list[Any] | None:
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None

    candidates = set(_TREE_NAMES) | set(_VALUES_NAMES)
    for node in ast.walk(parsed):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.lower() in candidates:
                if isinstance(node.value, ast.List):
                    values = _python_list_with_nulls(node.value)
                    if values:
                        return values
    return None


def _python_list_with_nulls(node: ast.List) -> list[Any] | None:
    values: list[Any] = []
    for element in node.elts:
        if _is_none_literal(element):
            values.append(None)
            continue
        try:
            literal_value = ast.literal_eval(element)
        except (ValueError, TypeError):
            return None
        if isinstance(literal_value, list):
            return None
        values.append(literal_value)
    return values if values else None


# --------------------------------------------------------------------------- #
# JavaScript nested object literal
# --------------------------------------------------------------------------- #
_JS_TREE_ASSIGN_RE = re.compile(r"\b(?:tree|root|bst)\w*\s*=\s*(\{)", re.IGNORECASE)

_JS_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
    |(?P<lbrace>\{)
    |(?P<rbrace>\})
    |(?P<colon>:)
    |(?P<comma>,)
    |(?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
    |(?P<number>-?\d+\.?\d*)
    |(?P<null>\bnull\b|\bNone\b)
    |(?P<ident>[A-Za-z_]\w*)
    """,
    re.VERBOSE,
)


def _extract_js_nested(code: str) -> dict[str, Any] | None:
    match = _JS_TREE_ASSIGN_RE.search(code)
    if not match:
        return None

    literal = _extract_balanced_braces(code, match.start(1))
    if literal is None:
        return None

    parsed = _parse_js_object_literal(literal)
    if not isinstance(parsed, dict):
        return None
    return _normalize_js_tree(parsed)


def _extract_balanced_braces(code: str, start: int) -> str | None:
    depth = 0
    for index in range(start, len(code)):
        char = code[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return code[start : index + 1]
    return None


def _tokenize_js(literal: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(literal):
        match = _JS_TOKEN_RE.match(literal, pos)
        if not match:
            pos += 1
            continue
        kind = match.lastgroup
        text = match.group()
        pos = match.end()
        if kind is None or kind == "ws":
            continue
        tokens.append((kind, text))
    return tokens


_JS_EOF: tuple[str, str] = ("eof", "")


class _JsValueParser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> tuple[str, str]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return _JS_EOF

    def _advance(self) -> tuple[str, str]:
        token = self._peek()
        self.pos += 1
        return token

    def parse_value(self) -> Any:
        kind, text = self._peek()
        if kind == "lbrace":
            return self.parse_object()
        if kind == "number":
            self._advance()
            return float(text) if "." in text else int(text)
        if kind == "string":
            self._advance()
            return text[1:-1]
        if kind == "null":
            self._advance()
            return None
        if kind == "ident":
            self._advance()
            return text
        self._advance()
        return None

    def parse_object(self) -> dict[str, Any]:
        self._advance()  # consume '{'
        obj: dict[str, Any] = {}
        while True:
            kind, text = self._peek()
            if kind in ("eof", "rbrace"):
                if kind == "rbrace":
                    self._advance()
                break
            if kind in ("ident", "string"):
                key = text.strip("\"'").lower()
                self._advance()
                if self._peek()[0] == "colon":
                    self._advance()
                obj[key] = self.parse_value()
            else:
                self._advance()
                continue
            if self._peek()[0] == "comma":
                self._advance()
        return obj


def _parse_js_object_literal(literal: str) -> dict[str, Any] | None:
    tokens = _tokenize_js(literal)
    if not tokens:
        return None
    result = _JsValueParser(tokens).parse_value()
    return result if isinstance(result, dict) else None


def _normalize_js_tree(obj: dict[str, Any]) -> dict[str, Any] | None:
    if "value" in obj:
        value = obj["value"]
    elif "val" in obj:
        value = obj["val"]
    elif "data" in obj:
        value = obj["data"]
    else:
        return None

    node: dict[str, Any] = {"value": value}
    left = obj.get("left")
    right = obj.get("right")
    if isinstance(left, dict):
        node["left"] = _normalize_js_tree(left)
    if isinstance(right, dict):
        node["right"] = _normalize_js_tree(right)
    return node


# --------------------------------------------------------------------------- #
# Generic flat array literal (C++ / Java / JS)
# --------------------------------------------------------------------------- #
_ASSIGN_LIST_RE = re.compile(
    r"\b(?:" + "|".join(_TREE_NAMES + _VALUES_NAMES) + r")\w*"
    r"\s*(?:\[[^\]]*\])?\s*=\s*(\{|\[)",
    re.IGNORECASE,
)


def _extract_generic_values(code: str) -> list[Any] | None:
    match = _ASSIGN_LIST_RE.search(code)
    if not match:
        return None

    literal = _extract_balanced_bracket(code, match.start(1))
    if literal is None:
        return None
    return _parse_flat_values(literal)


def _extract_balanced_bracket(code: str, start: int) -> str | None:
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


def _parse_flat_values(literal: str) -> list[Any] | None:
    translated = literal.replace("{", "[").replace("}", "]")
    translated = re.sub(r"\bnull\b", "None", translated)
    translated = re.sub(r"\bnullptr\b", "None", translated)
    try:
        value = ast.literal_eval(translated)
    except (ValueError, SyntaxError):
        return None

    if not isinstance(value, list) or not value:
        return None
    # A nested list means this is a graph/matrix literal, not a flat tree array.
    if any(isinstance(item, list) for item in value):
        return None
    return value


# --------------------------------------------------------------------------- #
# Tree construction from a flat list of values
# --------------------------------------------------------------------------- #
def _build_tree_from_values(values: list[Any]) -> dict[str, Any] | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    if any(v is None for v in values):
        return _build_level_order(values)
    return _build_bst(values)


def _build_level_order(values: list[Any]) -> dict[str, Any] | None:
    """Classic LeetCode-style level-order array with None/null gaps."""
    if not values or values[0] is None:
        return None

    root: dict[str, Any] = {"value": values[0]}
    queue: list[dict[str, Any]] = [root]
    index = 1
    total = len(values)

    while queue and index < total:
        current = queue.pop(0)
        if index < total:
            if values[index] is not None:
                left = {"value": values[index]}
                current["left"] = left
                queue.append(left)
            index += 1
        if index < total:
            if values[index] is not None:
                right = {"value": values[index]}
                current["right"] = right
                queue.append(right)
            index += 1

    return root


def _build_bst(values: list[Any]) -> dict[str, Any] | None:
    """Sequential BST insertion — the common textbook pattern of building a
    BST by inserting real values one at a time into an initially empty tree.
    """
    root: dict[str, Any] | None = None
    for value in values:
        root = _bst_insert(root, value)
    return root


def _bst_insert(node: dict[str, Any] | None, value: Any) -> dict[str, Any]:
    if node is None:
        return {"value": value}
    try:
        goes_left = value < node["value"]
    except TypeError:
        goes_left = str(value) < str(node["value"])

    if goes_left:
        node["left"] = _bst_insert(node.get("left"), value)
    else:
        node["right"] = _bst_insert(node.get("right"), value)
    return node


# --------------------------------------------------------------------------- #
# Shared traversal walkers (used by planners to compute the REAL visit order
# for whatever tree was extracted, instead of a hardcoded path).
# --------------------------------------------------------------------------- #
def walk_inorder(tree: dict[str, Any] | None) -> list[Any]:
    values: list[Any] = []

    def _visit(node: dict[str, Any] | None) -> None:
        if not node:
            return
        _visit(node.get("left"))
        values.append(node["value"])
        _visit(node.get("right"))

    _visit(tree)
    return values


def walk_preorder(tree: dict[str, Any] | None) -> list[Any]:
    values: list[Any] = []

    def _visit(node: dict[str, Any] | None) -> None:
        if not node:
            return
        values.append(node["value"])
        _visit(node.get("left"))
        _visit(node.get("right"))

    _visit(tree)
    return values


def walk_postorder(tree: dict[str, Any] | None) -> list[Any]:
    values: list[Any] = []

    def _visit(node: dict[str, Any] | None) -> None:
        if not node:
            return
        _visit(node.get("left"))
        _visit(node.get("right"))
        values.append(node["value"])

    _visit(tree)
    return values
