"""Trace Python snippets by running them under sys.settrace in a subprocess."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from tracing.driver import DriverPlan, Param, synthesize_args
from tracing.sandbox import parse_trace_output, run_sandboxed

RUNNER = Path(__file__).resolve().parent / "python_runner.py"
MAX_STEPS = 1500


def trace_python(code: str) -> dict[str, Any]:
    trace = _run(code)
    if trace["error"] or _has_user_calls(trace):
        return trace

    driver = _plan_driver(code, "sorted")
    if driver is None:
        return trace
    driven = _run(code + _render_call(driver))
    if _mutates_array_arg(driven, driver):
        driver = _plan_driver(code, "shuffled") or driver
        driven = _run(code + _render_call(driver))
    driven["driver"] = driver.to_dict()
    return driven


def _run(code: str) -> dict[str, Any]:
    result = run_sandboxed(
        [sys.executable, "-I", str(RUNNER)],
        stdin=json.dumps({"code": code, "max_steps": MAX_STEPS}),
    )
    return parse_trace_output(result, "python")


def _has_user_calls(trace: dict[str, Any]) -> bool:
    return any(step["event"] == "call" for step in trace["steps"])


def _plan_driver(code: str, variant: str) -> DriverPlan | None:
    """Pick the snippet's entry function and example arguments for it."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    candidates: list[tuple[str | None, ast.FunctionDef]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            candidates.append((None, node))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    candidates.append((node.name, item))

    # The entry point is the function no other function calls; with several,
    # take the last one defined (helpers are usually written first).
    called = {
        n.func.id if isinstance(n.func, ast.Name) else n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
    }
    entries = [c for c in candidates if c[1].name not in called] or candidates
    for owner, fn in reversed(entries):
        params = [
            Param(a.arg, ast.unparse(a.annotation) if a.annotation else "")
            for a in fn.args.args
            if a.arg not in {"self", "cls"}
        ]
        args = synthesize_args(params, variant)
        if args is not None:
            return DriverPlan(function=fn.name, owner_class=owner, args=args, variant=variant)
    return None


def _render_call(driver: DriverPlan) -> str:
    args = ", ".join(repr(value) for _name, value in driver.args)
    target = f"{driver.owner_class}().{driver.function}" if driver.owner_class else driver.function
    return f"\n\n{target}({args})\n"


def _mutates_array_arg(trace: dict[str, Any], driver: DriverPlan) -> bool:
    array_params = [name for name, value in driver.args if isinstance(value, list)]
    first: dict[str, Any] = {}
    for step in trace["steps"]:
        if step["func"] != driver.function:
            continue
        frame_locals = step["stack"][-1]["locals"]
        for name in array_params:
            value = frame_locals.get(name)
            if not isinstance(value, dict) or "ref" not in value:
                continue
            items = step["heap"].get(value["ref"], {}).get("items")
            if name not in first:
                first[name] = items
            elif items != first[name]:
                return True
    return False
