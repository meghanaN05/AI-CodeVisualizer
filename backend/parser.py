"""Parse source code into a language-neutral intermediate representation."""

from __future__ import annotations

from typing import Any

from cpp_parser import parse_cpp
from ir_analysis import enrich_ir
from java_parser import parse_java
from javascript_parser import parse_javascript
from python_parser import parse_python


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
        return parse_cpp(code)

    if normalized == "python":
        return parse_python(code)

    if normalized in {"javascript", "js"}:
        return parse_javascript(code)

    if normalized == "java":
        return parse_java(code)

    return enrich_ir(fallback_ir(code, normalized), code, normalized)


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
