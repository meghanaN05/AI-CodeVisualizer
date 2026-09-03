"""Semantic analyzer: parse source, extract entities, attach complexity."""

from __future__ import annotations

from typing import Any

from classifier import classify
from graph_extractor import extract_graph
from parser import parse_code
from visualization.complexity import analyze_complexity


def analyze(code: str, language: str) -> dict[str, Any]:
    ir = parse_code(code, language)
    classification = classify(code, language, ir)
    graph = extract_graph(code, language)
    complexity = analyze_complexity(
        ir,
        extra={"graph": graph or {}, "domain": classification["domain"]},
    )
    ir["classification"] = classification
    ir["extracted_graph"] = graph
    ir["complexity"] = complexity.model_dump()
    return ir
