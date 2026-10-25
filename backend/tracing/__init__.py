"""Execution tracing: run a snippet and record what it actually does.

Every language tracer produces the same JSON trace so the planner never needs
to know which language (or which algorithm) it is looking at:

    {
      "language": "python",
      "steps": [
        {
          "line": 5,                       # line ABOUT to execute (1-based)
          "event": "line" | "call" | "return",
          "func": "sort",                  # innermost user function
          "stack": [                       # outermost frame first
            {"func": "<module>", "locals": {"nums": {"ref": "1"}}},
            {"func": "sort", "locals": {"a": {"ref": "1"}, "j": 0}}
          ],
          "heap": {                        # objects reachable from locals
            "1": {"kind": "list", "items": [5, 1, 4, 2]}
          },
          "return_value": 3                # only on "return" events
        }
      ],
      "stdout": "...",
      "error": null | "message",
      "truncated": false,                  # hit the step limit
      "driver": null | {...}               # set when we synthesized a call
    }

Values are JSON scalars or {"ref": id}. Heap objects have a "kind" of list,
tuple, set, dict ("entries": [[k, v], ...]) or object ("class", "fields").
A heap id identifies the same program object across steps, so aliases
(a parameter and the caller's variable) and pointers resolve to one object.
"""

from __future__ import annotations

from typing import Any

from tracing.js_tracer import trace_javascript
from tracing.python_tracer import trace_python

TRACERS = {
    "python": trace_python,
    "javascript": trace_javascript,
}

LANGUAGE_ALIASES = {
    "py": "python",
    "js": "javascript",
    "c++": "cpp",
    "c": "cpp",
}


def normalize_language(language: str) -> str:
    lang = (language or "").strip().lower()
    return LANGUAGE_ALIASES.get(lang, lang)


def trace_code(code: str, language: str) -> dict[str, Any] | None:
    """Return the execution trace, or None when the language has no tracer."""
    tracer = TRACERS.get(normalize_language(language))
    if tracer is None:
        return None
    return tracer(code)
