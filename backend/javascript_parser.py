"""JavaScript parser using Tree-sitter."""

from __future__ import annotations

from typing import Any

import tree_sitter_javascript as tsjs

from ts_parser import parse_with_tree_sitter


def parse_javascript(code: str) -> dict[str, Any]:
    return parse_with_tree_sitter(code, "javascript", tsjs)
