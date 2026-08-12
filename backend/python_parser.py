"""Python parser using the built-in ast module."""

from __future__ import annotations

import ast
from typing import Any

from ir_analysis import enrich_ir


def parse_python(code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return enrich_ir(
            {
                "language": "python",
                "source_code": code,
                "parse_error": str(exc),
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
            },
            code,
            "python",
        )

    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    global_variables: list[dict[str, Any]] = []
    conditions: list[str] = []
    calls: list[dict[str, Any]] = []
    loops: list[dict[str, Any]] = []
    arrays: list[dict[str, Any]] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(_parse_class(node))
        elif isinstance(node, ast.FunctionDef):
            fn = _parse_function(node)
            functions.append(fn)
            conditions.extend(fn["conditions"])
            loops.extend(fn["loops"])
            calls.extend(_extract_calls(node, fn["name"]))
        elif isinstance(node, ast.Assign):
            global_variables.extend(_parse_assign(node, scope="global"))

    ir = {
        "language": "python",
        "source_code": code,
        "functions": functions,
        "classes": classes,
        "global_variables": global_variables,
        "variables": global_variables,
        "conditions": list(dict.fromkeys(conditions)),
        "calls": calls,
        "loops": loops,
        "arrays": arrays,
        "data_structures": [],
        "algorithm": None,
        "operations": [],
    }
    return enrich_ir(ir, code, "python")


def _parse_class(node: ast.ClassDef) -> dict[str, Any]:
    methods: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []

    for item in node.body:
        if isinstance(item, ast.FunctionDef):
            methods.append(_parse_function(item, class_name=node.name))
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            members.append(
                {
                    "name": item.target.id,
                    "type": ast.unparse(item.annotation) if item.annotation else "Any",
                    "line": item.lineno,
                }
            )
        elif isinstance(item, ast.Assign):
            members.extend(_parse_assign(item, scope="member"))

    return {"name": node.name, "members": members, "methods": methods, "line": node.lineno}


def _parse_function(
    node: ast.FunctionDef, class_name: str | None = None
) -> dict[str, Any]:
    fn_calls = _call_names(node)
    fn_conditions = [
        ast.unparse(child.test)
        for child in ast.walk(node)
        if isinstance(child, ast.If)
    ]
    fn_loops = [
        {
            "type": type(child).__name__.replace("Async", "").lower(),
            "function": node.name,
            "line": getattr(child, "lineno", None),
        }
        for child in ast.walk(node)
        if isinstance(child, (ast.For, ast.While))
    ]
    variables: list[dict[str, Any]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            variables.extend(_parse_assign(child, scope="local"))

    return {
        "name": node.name,
        "class": class_name,
        "return_type": "Any",
        "parameters": [{"name": arg.arg, "type": "Any"} for arg in node.args.args],
        "recursive": node.name in fn_calls,
        "conditions": fn_conditions,
        "calls": fn_calls,
        "loops": fn_loops,
        "variables": variables,
        "line": node.lineno,
    }


def _parse_assign(node: ast.Assign, scope: str) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    for target in node.targets:
        if isinstance(target, ast.Name):
            variables.append(
                {
                    "name": target.id,
                    "type": "Any",
                    "scope": scope,
                    "initializer": ast.unparse(node.value),
                    "line": getattr(node, "lineno", None),
                }
            )
        elif isinstance(target, ast.Subscript):
            variables.append(
                {
                    "name": ast.unparse(target),
                    "type": "Any",
                    "scope": scope,
                    "initializer": ast.unparse(node.value),
                    "line": getattr(node, "lineno", None),
                }
            )
    return variables


def _call_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                names.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                names.append(child.func.attr)
    return names


def _extract_calls(node: ast.AST, caller: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                fn = child.func.id
            elif isinstance(child.func, ast.Attribute):
                fn = child.func.attr
            else:
                continue
            result.append(
                {
                    "function": fn,
                    "arguments": [ast.unparse(arg) for arg in child.args],
                    "caller": caller,
                    "line": getattr(child, "lineno", None),
                }
            )
    return result
