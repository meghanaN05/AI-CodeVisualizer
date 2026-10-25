"""Execute a Python snippet under sys.settrace and print a JSON trace.

Runs as a standalone subprocess (python -I), so it must import only the
standard library. Reads {"code", "max_steps"} as JSON on stdin and writes
the trace (see tracing/__init__.py for the format) as JSON on stdout.
"""

from __future__ import annotations

import io
import json
import math
import sys
import types
from inspect import CO_OPTIMIZED

FILENAME = "<snippet>"
MAX_ITEMS = 64
MAX_DEPTH = 12


# Pasted solutions are often Python 2 (LeetCode-style); these names are the
# common ones that differ, mapped to their Python 3 equivalents.
PYTHON2_BUILTINS = {
    "xrange": range,
    "raw_input": input,
    "unicode": str,
    "basestring": str,
    "long": int,
    "unichr": chr,
    "reduce": __import__("functools").reduce,
}


class StepLimitReached(Exception):
    pass


class Encoder:
    """Encode Python values into trace values, collecting heap objects."""

    def __init__(self, ids: dict[int, int], keepalive: list[object]) -> None:
        self.ids = ids
        self.keepalive = keepalive
        self.heap: dict[str, dict] = {}

    def encode(self, value: object, depth: int = 0):
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            if math.isinf(value):
                return "∞" if value > 0 else "-∞"
            if math.isnan(value):
                return "NaN"
            return value
        if depth > MAX_DEPTH:
            return "…"

        ref = self._ref(value)
        if ref in self.heap:
            return {"ref": ref}
        self.heap[ref] = {}  # reserve first so cycles terminate

        if isinstance(value, (list, tuple)) or type(value).__name__ == "deque":
            kind = "tuple" if isinstance(value, tuple) else "list"
            items = [self.encode(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
            obj = {"kind": kind, "items": items}
        elif isinstance(value, (set, frozenset)):
            items = sorted(value, key=_sort_key)[:MAX_ITEMS]
            obj = {"kind": "set", "items": [self.encode(v, depth + 1) for v in items]}
        elif isinstance(value, dict):
            entries = [
                [self.encode(k, depth + 1), self.encode(v, depth + 1)]
                for k, v in list(value.items())[:MAX_ITEMS]
            ]
            obj = {"kind": "dict", "entries": entries}
        else:
            fields = _instance_fields(value)
            obj = {
                "kind": "object",
                "class": type(value).__name__,
                "fields": {k: self.encode(v, depth + 1) for k, v in fields.items()},
            }
        self.heap[ref] = obj
        return {"ref": ref}

    def _ref(self, value: object) -> str:
        key = id(value)
        if key not in self.ids:
            self.ids[key] = len(self.ids) + 1
            # Holding a reference keeps id() from being reused by a new
            # object, so one heap id always means one program object.
            self.keepalive.append(value)
        return str(self.ids[key])


def _sort_key(value: object):
    return (type(value).__name__, str(value))


def _instance_fields(value: object) -> dict[str, object]:
    fields = dict(getattr(value, "__dict__", {}) or {})
    for slot in getattr(type(value), "__slots__", ()) or ():
        if hasattr(value, slot):
            fields[slot] = getattr(value, slot)
    return {k: v for k, v in fields.items() if not k.startswith("__")}


def _is_visible(name: str, value: object) -> bool:
    if name.startswith("__"):
        return False
    return not isinstance(
        value,
        (types.ModuleType, types.FunctionType, types.BuiltinFunctionType, type),
    )


def _is_class_body(frame) -> bool:
    """Class bodies run as unoptimized frames; they are definitions, not calls."""
    code = frame.f_code
    return code.co_name != "<module>" and not code.co_flags & CO_OPTIMIZED


def main() -> None:
    request = json.loads(sys.stdin.read())
    code = request["code"]
    max_steps = int(request.get("max_steps", 1500))

    real_stdout = sys.stdout
    captured = io.StringIO()
    steps: list[dict] = []
    ids: dict[int, int] = {}
    keepalive: list[object] = []
    result = {"language": "python", "steps": steps, "error": None, "truncated": False}
    printed = {"length": 0}

    def snapshot(frame, event: str, arg) -> None:
        if len(steps) >= max_steps:
            result["truncated"] = True
            raise StepLimitReached()
        frames = []
        f = frame
        while f is not None:
            if f.f_code.co_filename == FILENAME and not _is_class_body(f):
                frames.append(f)
            f = f.f_back
        frames.reverse()

        encoder = Encoder(ids, keepalive)
        stack = []
        for f in frames:
            name = "<module>" if f.f_code.co_name == "<module>" else f.f_code.co_name
            local_vars = {
                k: encoder.encode(v)
                for k, v in f.f_locals.items()
                if _is_visible(k, v)
            }
            stack.append({"func": name, "locals": local_vars})

        step = {
            "line": frame.f_lineno,
            "event": event,
            "func": stack[-1]["func"] if stack else "<module>",
            "stack": stack,
            "heap": encoder.heap,
        }
        if event == "return":
            step["return_value"] = encoder.encode(arg)
        output = captured.getvalue()
        if len(output) > printed["length"]:
            step["stdout"] = output[printed["length"]:]
            printed["length"] = len(output)
        steps.append(step)

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != FILENAME:
            return None
        if _is_class_body(frame):
            return tracer
        if event in ("call", "line", "return"):
            if not (event == "call" and frame.f_code.co_name == "<module>"):
                if not (event == "return" and frame.f_code.co_name == "<module>"):
                    snapshot(frame, event, arg)
        return tracer

    namespace = {"__name__": "__main__", **PYTHON2_BUILTINS}
    try:
        compiled = compile(code, FILENAME, "exec")
    except SyntaxError as exc:
        result["error"] = f"SyntaxError: {exc.msg} (line {exc.lineno})"
        real_stdout.write(json.dumps(result))
        return

    sys.stdout = captured
    sys.settrace(tracer)
    try:
        exec(compiled, namespace)
    except StepLimitReached:
        pass
    except BaseException as exc:  # user code may raise anything, incl. SystemExit
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        sys.settrace(None)
        sys.stdout = real_stdout

    result["stdout"] = captured.getvalue()[-4000:]
    real_stdout.write(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
