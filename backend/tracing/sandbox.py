"""Run untrusted snippet code in a resource-limited subprocess.

This is a first line of defence for local development: a CPU-time limit, a
wall-clock timeout, a file-size limit, an empty environment and a throwaway
working directory. It does NOT block network or filesystem reads; production
must run the backend inside a locked-down container (no network, read-only
root, non-root user) on top of this.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CPU_SECONDS = 10
WALL_SECONDS = 20
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_CHARS = 400 * 1024 * 1024

# Every tracer stops after this many steps. It exists only so an infinite
# loop terminates; the video says when a run was cut off here.
MAX_TRACE_STEPS = 5000


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _limit_resources() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))


def run_sandboxed(
    command: list[str],
    stdin: str = "",
    cwd: Path | None = None,
    timeout: float = WALL_SECONDS,
) -> SandboxResult:
    preexec = _limit_resources if sys.platform != "win32" else None
    with tempfile.TemporaryDirectory(prefix="trace_") as scratch:
        try:
            proc = subprocess.run(
                command,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=str(cwd or scratch),
                env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
                preexec_fn=preexec,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(returncode=-1, stdout="", stderr="", timed_out=True)
    return SandboxResult(
        returncode=proc.returncode,
        stdout=proc.stdout[:MAX_OUTPUT_CHARS],
        stderr=proc.stderr[-4000:],
    )


def parse_trace_output(result: SandboxResult, language: str) -> dict[str, Any]:
    """Turn a tracer process result into a trace dict, never raising."""
    if result.timed_out:
        return _failed(language, f"Execution timed out after {WALL_SECONDS}s")
    try:
        trace = json.loads(result.stdout)
    except json.JSONDecodeError:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        return _failed(language, f"Tracer failed: {detail[-1500:]}")
    trace.setdefault("language", language)
    trace.setdefault("steps", [])
    trace.setdefault("error", None)
    trace.setdefault("truncated", False)
    return trace


def _failed(language: str, error: str) -> dict[str, Any]:
    return {"language": language, "steps": [], "error": error, "truncated": False}
