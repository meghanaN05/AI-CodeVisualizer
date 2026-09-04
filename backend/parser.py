"""Parse source code into a language-neutral intermediate representation."""

from __future__ import annotations

from typing import Any

from cpp_parser import parse_cpp
from graph_extractor import extract_graph
from ir_analysis import enrich_ir
from java_parser import parse_java
from javascript_parser import parse_javascript
from python_parser import parse_python
from tree_extractor import extract_tree

SUPPORTED_LANGUAGES = {
    "cpp",
    "c++",
    "c",
    "python",
    "javascript",
    "js",
    "java",
}


def parse_code(code: str, language: str) -> dict[str, Any]:
    normalized = language.strip().lower()

    if normalized in {"cpp", "c++", "c"}:
        ir = parse_cpp(code)
    elif normalized == "python":
        ir = parse_python(code)
    elif normalized in {"javascript", "js"}:
        ir = parse_javascript(code)
    elif normalized == "java":
        ir = parse_java(code)
    else:
        ir = enrich_ir(fallback_ir(code, normalized), code, normalized)

    ir["extracted_graph"] = extract_graph(code, normalized)
    ir["extracted_tree"] = extract_tree(code, normalized)
    return ir


def fallback_ir(code: str, language: str) -> dict[str, Any]:
    return {
        "language": language,
        "source_code": code,
        "functions": [],
        "classes": [],
        "global_variables": [],
        "variables": [],
        "conditions": [],
        "calls": [],
        "loops": [],
        "arrays": [],
        "data_structures": [],
        "algorithm": None,
        "operations": [],
        "unsupported_language": True,
    }
