"""Trace C++ snippets by compiling an instrumented copy and running it.

tracing/cpp/instrument.py rewrites the snippet (tree-sitter-cpp) so each
statement first calls a probe from the header-only runtime
tracing/cpp/include/cvt_runtime.hpp; the probe serializes every variable in
scope and prints one JSON step per line. Compile and run are separate
sandboxed processes. The resulting trace has the same shape as the Python
tracer's (see tracing/__init__.py).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import signal
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from tracing.cpp.instrument import FunctionInfo, Instrumented, ParamInfo, instrument
from tracing.driver import DriverPlan, Param, candidate_args
from tracing.python_tracer import _mutates_array_arg
from tracing.sandbox import WALL_SECONDS, run_sandboxed

INCLUDE_DIR = Path(__file__).resolve().parent / "cpp" / "include"
SUPPORT_SOURCE = Path(__file__).resolve().parent / "cpp" / "cvt_support.cpp"
MAX_STEPS = 1500
COMPILE_SECONDS = 60
CXX = os.environ.get("CVT_CXX") or shutil.which("g++") or shutil.which("clang++") or "g++"
CXX_FLAGS = ["-std=c++17", "-O0", "-w", "-fdiagnostics-color=never", f"-DCVT_MAX_STEPS={MAX_STEPS}"]
MARKER = "\x1e"
LANGUAGE = "cpp"

_CACHE_SIZE = 16
_binaries: OrderedDict[str, Path] = OrderedDict()
_cache_lock = threading.Lock()
_cache_dir: Path | None = None


def _cache_root() -> Path:
    global _cache_dir
    with _cache_lock:
        if _cache_dir is None:
            _cache_dir = Path(tempfile.mkdtemp(prefix="cvt_bin_"))
            atexit.register(shutil.rmtree, _cache_dir, True)
        return _cache_dir


def trace_cpp(code: str) -> dict[str, Any]:
    try:
        return _trace(code)
    except Exception as exc:  # a tracer bug must never take the backend down
        return _failed(f"C++ tracer error: {type(exc).__name__}: {exc}")


def _trace(code: str) -> dict[str, Any]:
    plan = instrument(code)
    if plan.has_main:
        binary, error = _build(code, plan, "")
        return _execute(binary) if binary else _failed(error)
    return _trace_with_driver(code, plan)


def _trace_with_driver(code: str, plan: Instrumented) -> dict[str, Any]:
    """No main(): call the entry function with synthesized example inputs.

    Every candidate input (ascending and shuffled arrays, a few scalar
    choices) is compiled into ONE binary that runs the candidate named by
    argv[1]; like the Python tracer we keep the run covering the most lines,
    and prefer shuffled inputs when the function rearranges its array.
    """
    entry = _entry_point(plan)
    if entry is None:
        error = _compile_error(plan.check_source)
        return _failed(error or "No main() function and no function that can be called with example inputs")
    fn, sorted_sets, shuffled_sets = entry
    binary, error = _build(code, plan, _render_main(plan, fn, sorted_sets + shuffled_sets))
    if binary is None:
        return _failed(error)

    def best_of(start: int, arg_sets: list, variant: str):
        best = None
        for offset, args in enumerate(arg_sets):
            trace = _execute(binary, start + offset)
            score = (not trace["error"], _lines_covered(trace))
            if best is None or score > best[0]:
                best = (score, DriverPlan(fn.name, fn.owner, args, variant), trace)
        return best[1], best[2]

    driver, trace = best_of(0, sorted_sets, "sorted")
    if shuffled_sets and not trace["error"] and _mutates_array_arg(trace, driver):
        driver, trace = best_of(len(sorted_sets), shuffled_sets, "shuffled")
    trace["driver"] = driver.to_dict()
    return trace


def _lines_covered(trace: dict[str, Any]) -> int:
    return len({s["line"] for s in trace["steps"] if s["func"] != "main"})


# --------------------------------------------------------------- compile/run


def _build(code: str, plan: Instrumented, driver_main: str) -> tuple[Path | None, str]:
    """Compile the instrumented program.

    When that fails but the user's own code compiles, the instrumentation
    tripped over something; leave the functions the compiler complained
    about untraced and try again rather than giving up.
    """
    binary, stderr = _compile(plan.source + driver_main)
    if binary is not None:
        return binary, ""
    user_error = _compile_error(plan.check_source)
    if user_error:
        return None, user_error
    skip: set[int] = set()
    for _attempt in range(2):
        lines = {int(n) for n in re.findall(r"main\.cpp:(\d+):", stderr)}
        if not lines - skip:
            break
        skip |= lines
        retry = instrument(code, frozenset(skip))
        binary, stderr = _compile(retry.source + driver_main)
        if binary is not None:
            return binary, ""
    return None, f"Could not trace this C++ code (instrumentation failed): {_trim_diagnostics(stderr)}"


def _execute(binary: Path, candidate: int | None = None) -> dict[str, Any]:
    command = [str(binary)] + ([str(candidate)] if candidate is not None else [])
    return _parse(run_sandboxed(command))  # fresh scratch cwd per run


def _compile(source: str) -> tuple[Path | None, str]:
    support, error = _support_object()
    if support is None:
        return None, error
    key = hashlib.sha256((CXX + " ".join(CXX_FLAGS) + support.name + source).encode()).hexdigest()[:24]
    with _cache_lock:
        cached = _binaries.get(key)
        if cached is not None and cached.exists():
            _binaries.move_to_end(key)
            return cached, ""
    workdir = Path(tempfile.mkdtemp(prefix=f"{key}_", dir=_cache_root()))
    (workdir / "main.cpp").write_text(source, encoding="utf8")
    result = run_sandboxed(
        [CXX, *CXX_FLAGS, "-I", str(INCLUDE_DIR), "main.cpp", str(support), "-o", "prog"],
        cwd=workdir,
        timeout=COMPILE_SECONDS,
    )
    binary = workdir / "prog"
    if result.timed_out or result.returncode != 0 or not binary.exists():
        shutil.rmtree(workdir, ignore_errors=True)
        return None, "compiler timed out" if result.timed_out else result.stderr
    with _cache_lock:
        existing = _binaries.get(key)
        if existing is not None and existing.exists():  # a concurrent request won
            shutil.rmtree(workdir, ignore_errors=True)
            return existing, ""
        _binaries[key] = binary
        while len(_binaries) > _CACHE_SIZE:
            _old_key, old = _binaries.popitem(last=False)
            shutil.rmtree(old.parent, ignore_errors=True)
    return binary, ""


_support_lock = threading.Lock()


def _support_object() -> tuple[Path | None, str]:
    """The runtime's process-level half, compiled once per runtime version."""
    digest = hashlib.sha256(CXX.encode() + " ".join(CXX_FLAGS).encode())
    for path in [SUPPORT_SOURCE, *sorted(INCLUDE_DIR.glob("*.hpp"))]:
        digest.update(path.read_bytes())
    target = _cache_root() / f"cvt_support_{digest.hexdigest()[:16]}.o"
    with _support_lock:
        if target.exists():
            return target, ""
        result = run_sandboxed(
            [CXX, *CXX_FLAGS, "-I", str(INCLUDE_DIR), "-c", str(SUPPORT_SOURCE), "-o", str(target)],
            cwd=_cache_root(),
            timeout=COMPILE_SECONDS,
        )
        if result.timed_out or result.returncode != 0 or not target.exists():
            return None, "runtime build failed: " + (result.stderr.strip()[-600:] or "timed out")
        return target, ""


def _compile_error(code: str) -> str | None:
    """The compiler's complaint about the user's own code, or None if it compiles."""
    with tempfile.TemporaryDirectory(prefix="cvt_chk_") as tmp:
        Path(tmp, "main.cpp").write_text(code, encoding="utf8")
        result = run_sandboxed(
            [CXX, *CXX_FLAGS, "-I", str(INCLUDE_DIR), "-fsyntax-only", "main.cpp"],
            cwd=Path(tmp),
            timeout=COMPILE_SECONDS,
        )
    if result.timed_out:
        return "Compile error: compiler timed out"
    if result.returncode == 0:
        return None
    return "Compile error: " + _trim_diagnostics(result.stderr)


_DIAG = re.compile(r"^(?:.*?main\.cpp):(\d+):(?:(\d+):)?\s*(?:fatal )?error:\s*(.*)$")


def _trim_diagnostics(stderr: str) -> str:
    errors = []
    for line in stderr.splitlines():
        match = _DIAG.match(line.strip())
        if match:
            errors.append(f"line {match.group(1)}: {match.group(3).strip()}")
        if len(errors) == 3:
            break
    text = "; ".join(errors) if errors else stderr.strip()
    return text[:600]


def _parse(result) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    for raw in result.stdout.split("\n"):
        start = raw.find(MARKER)
        if start < 0:
            continue
        try:
            record = json.loads(raw[start + 1 :])
        except json.JSONDecodeError:
            continue  # cut off by the output limit
        if record.get("final"):
            final = record
        else:
            steps.append(record)

    trace: dict[str, Any] = {
        "language": LANGUAGE,
        "steps": steps,
        "stdout": "",
        "error": None,
        "truncated": False,
    }
    if final is not None:
        trace["stdout"] = final.get("stdout") or ""
        trace["error"] = final.get("error")
        trace["truncated"] = bool(final.get("truncated"))
    if trace["error"] is None and not trace["truncated"]:
        trace["error"] = _exit_error(result, final is None)
    return trace


def _exit_error(result, missing_final: bool) -> str | None:
    if result.timed_out:
        return f"Execution timed out after {WALL_SECONDS}s"
    code = result.returncode
    if code < 0:
        if -code == signal.SIGKILL:
            return "Program was killed (CPU time or memory limit exceeded)"
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = f"signal {-code}"
        return f"Program killed by {name}"
    if code != 0:
        return f"Program exited with code {code}"
    if missing_final:
        detail = result.stderr.strip()[-300:]
        return "Tracer produced no result" + (f": {detail}" if detail else "")
    return None


def _failed(error: str) -> dict[str, Any]:
    return {"language": LANGUAGE, "steps": [], "stdout": "", "error": error, "truncated": False}


# -------------------------------------------------------------------- driver


def _entry_point(inst: Instrumented) -> tuple[FunctionInfo, list, list] | None:
    """The function nothing else calls (last defined wins) and its inputs."""
    candidates = [f for f in inst.functions if f.is_public]

    def called_by_others(f: FunctionInfo) -> bool:
        return any(f.name in g.calls for g in inst.functions if g is not f)

    entries = [f for f in candidates if not called_by_others(f)] or candidates
    for fn in reversed(entries):
        params = [Param(p.name, _driver_hint(p, inst)) for p in fn.params]
        sorted_sets = [a for a in candidate_args(params, "sorted") if _renderable(fn, a, inst)]
        if not sorted_sets:
            continue
        shuffled_sets = [a for a in candidate_args(params, "shuffled") if _renderable(fn, a, inst)]
        if not any(isinstance(v, list) for _n, v in sorted_sets[0]):
            shuffled_sets = []
        return fn, sorted_sets, shuffled_sets
    return None


def _renderable(fn: FunctionInfo, args: list, inst: Instrumented) -> bool:
    return all(
        isinstance(value, list) or not _node_kind(param, inst)
        for param, (_name, value) in zip(fn.params, args)
    )


def _node_kind(p: ParamInfo, inst: Instrumented) -> str | None:
    """'list' / 'tree' for ListNode*/TreeNode*-style pointer parameters."""
    if p.pointer != 1 or p.array:
        return None
    base = p.base_type.replace("struct ", "").strip()
    if base == "ListNode" or (base in inst.used_leetcode_types and base == "ListNode"):
        return "list"
    if base == "TreeNode":
        return "tree"
    return None


def _driver_hint(p: ParamInfo, inst: Instrumented) -> str:
    if _node_kind(p, inst):
        return "vector<int>"
    return p.hint


def _render_main(inst: Instrumented, fn: FunctionInfo, arg_sets: list[list[tuple[str, Any]]]) -> str:
    """A main() that calls fn with the argument set chosen by argv[1]."""
    lines = [
        "\nint main(int CVTargc_, char** CVTargv_) {",
        'cvt_rt::Frame CVTf_("main", 0, true); using namespace std;',
        "int CVTk_ = CVTargc_ > 1 ? CVTargv_[1][0] - '0' : 0;",
    ]
    for k, args in enumerate(arg_sets):
        lines.append(f"if (CVTk_ == {k}) {{")
        lines.extend(_render_call(inst, fn, [value for _name, value in args]))
        lines.append("}")
    lines.append("return 0; }\n")
    return "\n".join(lines)


def _render_call(inst: Instrumented, fn: FunctionInfo, values: list[Any]) -> list[str]:
    lines = []
    call_args = []
    for index, (param, value) in enumerate(zip(fn.params, values)):
        var = f"CVTa{index}_"
        kind = _node_kind(param, inst)
        base = param.base_type
        if kind == "list":
            lines.append(f"{base}* {var} = nullptr; {{ {base}** t = &{var};")
            for v in value:
                lines.append(f"*t = new {base}({_literal(v, base)}); t = &(*t)->next;")
            lines.append("}")
        elif kind == "tree":
            lines.append(f"{base}* {var} = {_bst(sorted(value), base)};")
        elif param.array or (param.pointer == 1 and isinstance(value, list)):
            items = ", ".join(_literal(v, base) for v in value)
            lines.append(f"{base} {var}[] = {{{items}}};")
            lines.append(f'cvt_rt::Arr CVTh{index}_("{param.name}", {var}, {len(value)}, cvt_rt::HIDDEN);')
        else:
            lines.append(f"{base} {var} = {_literal(value, base)};")
        call_args.append(var)
    args = ", ".join(call_args)
    if fn.owner and fn.is_static:
        lines.append(f"{fn.owner}::{fn.name}({args});")
    elif fn.owner:
        lines.append(f"{fn.owner} CVTobj_; CVTobj_.{fn.name}({args});")
    else:
        lines.append(f"{fn.name}({args});")
    return lines


def _bst(values: list[Any], base: str) -> str:
    if not values:
        return "nullptr"
    mid = len(values) // 2
    left, right = _bst(values[:mid], base), _bst(values[mid + 1 :], base)
    node = f"new {base}({_literal(values[mid], base)})"
    if left == right == "nullptr":
        return node
    return f"[&]{{ {base}* n = {node}; n->left = {left}; n->right = {right}; return n; }}()"


def _literal(value: Any, type_text: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        if "char" in type_text and "string" not in type_text and len(value) == 1:
            return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        return json.dumps(value)
    if isinstance(value, list):
        return "{" + ", ".join(_literal(v, type_text) for v in value) + "}"
    return json.dumps(str(value))
