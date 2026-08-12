"""Java parser using Tree-sitter."""

from __future__ import annotations

from typing import Any

import tree_sitter_java as tsjava

from ts_parser import parse_with_tree_sitter


def parse_java(code: str) -> dict[str, Any]:
    return parse_with_tree_sitter(code, "java", tsjava)
