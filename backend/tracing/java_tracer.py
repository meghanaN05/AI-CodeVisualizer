"""Trace Java snippets with the Java Debug Interface (JDI).

`java/Tracer.java` compiles the snippet in-process (javac -g, for local
variable names) and runs it in a debuggee JVM, stepping line by line through
the user's classes only, and prints a trace in the shared format (see
tracing/__init__.py). This module prepares the source and drives it:

* Original line numbers are preserved. A snippet without a class wrapper (a
  bare method, or bare statements) is wrapped by inserting text on existing
  lines, and default imports are prepended on line 1.
* A snippet without `main` (LeetCode-style `class Solution`) gets a separate
  driver class appended after the code, which calls the entry method with
  example arguments from tracing.driver, exactly like the Python tracer.

The compiled tracer is cached per JDK in the system temp dir, so requests
only pay for the snippet compile and the debuggee run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracing.driver import DriverPlan, Param, synthesize_args
from tracing.python_tracer import _mutates_array_arg
from tracing.sandbox import MAX_TRACE_STEPS, parse_trace_output, run_sandboxed

JAVA_DIR = Path(__file__).resolve().parent / "java"
MAX_STEPS = MAX_TRACE_STEPS
DEBUG_DEADLINE_MS = 15000  # tracer-side limit for the traced program
SANDBOX_TIMEOUT = 25.0  # JVM start + compile + DEBUG_DEADLINE_MS, bounded
DRIVER_CLASS = "__TraceDriver"
DEFAULT_IMPORTS = (
    "import java.util.*;import java.util.function.*;import java.util.stream.*;"
    "import java.io.*;import java.math.*; "
)
JVM_FLAGS = ["-XX:TieredStopAtLevel=1", "-XX:+UseSerialGC", "-XX:-UsePerfData", "-Xshare:auto", "-Xmx384m"]

_TYPE_DECLS = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
_COMMENTS = {"line_comment", "block_comment"}
_LIST_TYPES = {"List", "ArrayList", "Collection", "Iterable", "AbstractList", "LinkedList"}
_SET_TYPES = {"Set", "HashSet", "LinkedHashSet", "TreeSet", "SortedSet"}
_QUEUE_TYPES = {"Queue", "Deque", "ArrayDeque"}
_MAP_TYPES = {"Map", "HashMap", "TreeMap", "LinkedHashMap", "SortedMap"}
_INT_TYPES = {"int", "Integer", "long", "Long", "short", "Short", "byte", "Byte"}
_FLOAT_TYPES = {"double", "Double", "float", "Float"}


def trace_java(code: str) -> dict[str, Any]:
    java = _java_home()
    if java is None:
        return _failed("Java tracing needs a JDK (java + javac 11+) on the server")
    try:
        tracer_dir = _tracer_classes(java)
    except RuntimeError as exc:
        return _failed(str(exc))

    program = prepare(code)
    trace: dict[str, Any] | None = None
    if program.main_class:
        trace = _run(java, tracer_dir, program, program.source, program.main_class)
        if trace["error"] or _has_user_calls(trace):
            return trace

    driver = _plan_driver(program, "sorted")
    if driver is None:
        if trace is not None:
            return trace
        # Nothing to run; still compile so syntax errors are reported.
        return _run(java, tracer_dir, program, program.source, "-")

    driven = _run(java, tracer_dir, program, program.source + _render_driver(program, driver), DRIVER_CLASS)
    if _mutates_array_arg(driven, driver):
        shuffled = _plan_driver(program, "shuffled")
        if shuffled is not None:
            driver = shuffled
            driven = _run(java, tracer_dir, program, program.source + _render_driver(program, driver), DRIVER_CLASS)
    driven["driver"] = driver.to_dict()
    return driven


# ---------------------------------------------------------------- running


def _run(java: Path, tracer_dir: Path, program: Program, source: str, main_class: str) -> dict[str, Any]:
    filename, line_count = program.filename, program.line_count
    with tempfile.TemporaryDirectory(prefix="javatrace_") as work:
        work_path = Path(work)
        src = work_path / filename
        src.write_text(source, encoding="utf-8")
        classes = work_path / "classes"
        command = [
            str(java / "bin" / "java"),
            *JVM_FLAGS,
            "-cp",
            str(tracer_dir / "tracer"),
            "Tracer",
            str(src),
            str(classes),
            main_class,
            str(MAX_STEPS),
            str(DEBUG_DEADLINE_MS),
            str(tracer_dir / "boot"),
        ]
        result = run_sandboxed(command, cwd=work_path, timeout=SANDBOX_TIMEOUT)
    trace = parse_trace_output(result, "java")
    trace.setdefault("stdout", "")
    # Our wrapper's closing braces sit below the snippet; their "line" steps
    # point at code the user never wrote.
    trace["steps"] = [s for s in trace["steps"] if s["event"] != "line" or s["line"] <= line_count]
    return trace


def _failed(error: str) -> dict[str, Any]:
    return {"language": "java", "steps": [], "error": error, "truncated": False, "stdout": ""}


def _has_user_calls(trace: dict[str, Any]) -> bool:
    return any(step["event"] == "call" for step in trace["steps"])


_java_lock = threading.Lock()
_java_cache: dict[str, Path | None] = {}


def _java_home() -> Path | None:
    """Locate a JDK once: $JAVA_HOME, else ask the `java` on PATH for java.home."""
    with _java_lock:
        if "home" in _java_cache:
            return _java_cache["home"]
        home: Path | None = None
        candidates = [os.environ.get("JAVA_HOME")]
        java = shutil.which("java")
        if java:
            try:
                probe = subprocess.run(
                    [java, "-XshowSettings:properties", "-version"],
                    capture_output=True, text=True, timeout=20,
                )
                match = re.search(r"^\s*java\.home = (.+)$", probe.stderr, re.MULTILINE)
                if match:
                    candidates.append(match.group(1).strip())
            except (OSError, subprocess.SubprocessError):
                pass
        for candidate in candidates:
            if candidate and (Path(candidate) / "bin" / "javac").exists():
                home = Path(candidate)
                break
        _java_cache["home"] = home
        return home


def _tracer_classes(java: Path) -> Path:
    """Compile Tracer.java/TraceBoot.java once per JDK + source version."""
    sources = [JAVA_DIR / "Tracer.java", JAVA_DIR / "TraceBoot.java"]
    digest = hashlib.sha256(str(java).encode())
    for path in sources:
        digest.update(path.read_bytes())
    root = Path(os.environ.get("JAVA_TRACER_CACHE", Path(tempfile.gettempdir()) / "codeviz-java-tracer"))
    target = root / digest.hexdigest()[:16]
    if (target / "tracer" / "Tracer.class").exists() and (target / "boot" / "TraceBoot.class").exists():
        return target

    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="build_", dir=root))
    javac = str(java / "bin" / "javac")
    for name, src in (("tracer", sources[0]), ("boot", sources[1])):
        proc = subprocess.run(
            [javac, "-nowarn", "-d", str(staging / name), str(src)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(f"Could not build the Java tracer: {proc.stderr[-800:]}")
    try:
        staging.rename(target)
    except OSError:  # another worker won the race
        shutil.rmtree(staging, ignore_errors=True)
    return target


# ------------------------------------------------------------ preparation


@dataclass
class Method:
    name: str
    owner: str | None  # None: the method lives in our wrapper class
    params: list[tuple[str, str]]  # (java type, name)
    is_static: bool
    is_public: bool


@dataclass
class Program:
    source: str
    filename: str
    main_class: str | None
    wrapper: str | None
    line_count: int = 0
    methods: list[Method] = field(default_factory=list)
    called: set[str] = field(default_factory=set)


def _parser():
    import tree_sitter_java
    from tree_sitter import Language, Parser

    return Parser(Language(tree_sitter_java.language()))


def prepare(code: str) -> Program:
    """Make the snippet a compilable file without moving any original line."""
    code = code.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    code = re.sub(r"^[ \t]*package\s+[\w.]+\s*;", lambda m: " " * len(m.group(0)), code, flags=re.MULTILINE)
    data = code.encode("utf-8")
    try:
        tree = _parser().parse(data)
    except Exception:  # tree-sitter missing or broken: compile as-is
        return Program(DEFAULT_IMPORTS + code, _filename_for(code, None), _regex_main(code), None, code.count("\n") + 1)

    root = tree.root_node
    top = [n for n in root.named_children if n.type not in _COMMENTS]
    body = [n for n in top if n.type not in ("import_declaration", "package_declaration")]
    has_types = any(n.type in _TYPE_DECLS for n in body)
    loose = [n for n in body if n.type not in _TYPE_DECLS]

    if not loose or (root.has_error and has_types):
        mode = "class"
    elif all(n.type in ("method_declaration", "local_variable_declaration") for n in loose):
        mode = "members"
    else:
        mode = "script"

    inserts: list[tuple[int, str]] = []
    wrapper = None
    if mode != "class":
        wrapper = "Snippet" if re.search(r"\b(class|interface|enum|record)\s+Main\b", code) else "Main"
        first = body[0].start_byte if body else len(data)
        inserts.append((first, f"public class {wrapper} {{ "))
        main_opened = False
        for node in body:
            is_decl = node.type in _TYPE_DECLS or node.type == "method_declaration"
            if mode == "script" and not is_decl and not main_opened:
                inserts.append((node.start_byte, "public static void main(String[] args) throws Throwable { "))
                main_opened = True
            if not main_opened and (is_decl or node.type == "local_variable_declaration") and not _has_modifier(node, "static"):
                inserts.append((node.start_byte, "static "))
        tail = "\n}" + ("}" if main_opened else "") + "\n"
    else:
        tail = ""

    # Apply from the end; at equal offsets the later insert goes in first so
    # earlier inserts end up in front ("class Main { " before "static ").
    for _order, (offset, text) in sorted(enumerate(inserts), key=lambda item: (item[1][0], item[0]), reverse=True):
        data = data[:offset] + text.encode("utf-8") + data[offset:]
    source = DEFAULT_IMPORTS + data.decode("utf-8") + tail

    program = Program(source, "Main.java", None, wrapper)
    if wrapper:
        program.filename = f"{wrapper}.java"
        if mode == "script" or any(n.type == "method_declaration" and _text(n.child_by_field_name("name")) == "main" for n in loose):
            program.main_class = wrapper
    else:
        program.filename = _filename_for(code, root)

    program.line_count = code.count("\n") + 1
    _collect_methods(root, program, mode)
    return program


def _collect_methods(root, program: Program, mode: str) -> None:
    def walk(node):
        yield node
        for child in node.children:
            yield from walk(child)

    for node in walk(root):
        if node.type == "method_invocation":
            name = node.child_by_field_name("name")
            if name is not None:
                program.called.add(_text(name))

    for node in root.named_children:
        if mode != "class" and node.type == "method_declaration":
            _add_method(program, node, None, True)
        elif node.type == "class_declaration" and mode == "class":
            cls = _text(node.child_by_field_name("name"))
            class_body = node.child_by_field_name("body")
            members = class_body.named_children if class_body else []
            ctors = [m for m in members if m.type == "constructor_declaration"]
            # `new Owner()` must compile for instance methods to be callable.
            no_arg = not ctors or any(not (m.child_by_field_name("parameters") or m).named_children for m in ctors)
            for member in members:
                if member.type == "method_declaration" and not no_arg and not _has_modifier(member, "static"):
                    continue
                if member.type == "method_declaration":
                    _add_method(program, member, cls, False)
                    if _text(member.child_by_field_name("name")) == "main" and _has_modifier(member, "static"):
                        if program.main_class is None or _has_modifier(node, "public"):
                            program.main_class = cls


def _add_method(program: Program, node, owner: str | None, wrapped: bool) -> None:
    name = _text(node.child_by_field_name("name"))
    if name == "main" or node.child_by_field_name("body") is None:
        return
    if _has_modifier(node, "private") and owner is not None:
        return
    params: list[tuple[str, str]] = []
    plist = node.child_by_field_name("parameters")
    for p in plist.named_children if plist else []:
        if p.type == "formal_parameter":
            ptype = _text(p.child_by_field_name("type"))
            pname = _text(p.child_by_field_name("name"))
            dims = p.child_by_field_name("dimensions")
            params.append((ptype + (_text(dims) if dims else ""), pname))
        elif p.type == "spread_parameter":
            words = [c for c in p.named_children if c.type != "modifiers"]
            ptype = _text(words[0]) if words else "Object"
            declarator = next((c for c in p.named_children if c.type == "variable_declarator"), None)
            pname = _text(declarator.child_by_field_name("name")) if declarator else "args"
            params.append((ptype + "[]", pname))
    program.methods.append(
        Method(
            name=name,
            owner=owner,
            params=params,
            is_static=wrapped or owner is None or _has_modifier(node, "static"),
            is_public=_has_modifier(node, "public"),
        )
    )


def _has_modifier(node, word: str) -> bool:
    for child in node.children:
        if child.type == "modifiers":
            return any(_text(m) == word for m in child.children)
    return False


def _text(node) -> str:
    return node.text.decode("utf-8") if node is not None else ""


def _filename_for(code: str, root) -> str:
    if root is not None:
        for node in root.named_children:
            if node.type in _TYPE_DECLS and _has_modifier(node, "public"):
                return f"{_text(node.child_by_field_name('name'))}.java"
        return "Main.java"
    match = re.search(r"^\s*public\s+(?:final\s+|abstract\s+)*(?:class|interface|enum|record)\s+(\w+)", code, re.MULTILINE)
    return f"{match.group(1)}.java" if match else "Main.java"


def _regex_main(code: str) -> str | None:
    if not re.search(r"\bstatic\s+void\s+main\s*\(", code):
        return None
    match = re.search(r"(?:class|interface|enum|record)\s+(\w+)", code)
    return match.group(1) if match else None


# ----------------------------------------------------------------- driver


def _plan_driver(program: Program, variant: str) -> DriverPlan | None:
    """Pick the entry method (not called elsewhere, public preferred, last defined)."""
    candidates = program.methods
    entries = [m for m in candidates if m.name not in program.called] or candidates
    entries = [m for m in entries if m.is_public] or entries
    for method in reversed(entries):
        params = [Param(name, _type_hint(jtype)) for jtype, name in method.params]
        args = synthesize_args(params, variant)
        if args is None:
            continue
        if any(_render_value(jtype, value) is None for (jtype, _n), (_name, value) in zip(method.params, args)):
            continue
        return DriverPlan(function=method.name, owner_class=method.owner, args=args, variant=variant)
    return None


def _find_method(program: Program, driver: DriverPlan) -> Method:
    return next(m for m in reversed(program.methods) if m.name == driver.function and m.owner == driver.owner_class)


def _render_driver(program: Program, driver: DriverPlan) -> str:
    method = _find_method(program, driver)
    args = ", ".join(_render_value(jtype, value) or "null" for (jtype, _n), (_name, value) in zip(method.params, driver.args))
    owner = method.owner or program.wrapper
    target = f"{owner}.{method.name}" if method.is_static else f"new {owner}().{method.name}"
    return f"\nclass {DRIVER_CLASS} {{ public static void main(String[] args) throws Throwable {{ {target}({args}); }} }}\n"


def _split_type(jtype: str) -> tuple[str, list[str], int]:
    """'List<List<Integer>>[]' -> ('List', ['List<Integer>'], 1)."""
    text = re.sub(r"@\w+\s*", "", jtype).replace("final ", "").strip()
    dims = 0
    while text.endswith("[]"):
        dims += 1
        text = text[:-2].rstrip()
    if "<" not in text:
        return text.split(".")[-1], [], dims
    raw, inner = text.split("<", 1)
    inner = inner.rsplit(">", 1)[0]
    args, depth, current = [], 0, ""
    for char in inner:
        if char == "," and depth == 0:
            args.append(current.strip())
            current = ""
            continue
        depth += char == "<"
        depth -= char == ">"
        current += char
    if current.strip():
        args.append(current.strip())
    return raw.strip().split(".")[-1], args, dims


def _type_hint(jtype: str) -> str:
    """Java type -> the hint vocabulary tracing.driver understands."""
    raw, args, dims = _split_type(jtype)
    if dims:
        return _type_hint(raw) + "[]" * dims
    if raw in _LIST_TYPES | _SET_TYPES | _QUEUE_TYPES:
        return _type_hint(args[0] if args else "Integer") + "[]"
    if raw in _MAP_TYPES:
        return "map"
    if raw in _INT_TYPES:
        return "int"
    if raw in _FLOAT_TYPES:
        return "double"
    if raw in ("boolean", "Boolean"):
        return "bool"
    if raw in ("String", "CharSequence"):
        return "str"
    if raw in ("char", "Character"):
        return "char"
    return "object"


def _render_value(jtype: str, value: Any) -> str | None:
    """A Java expression of type `jtype` for `value`, or None if it doesn't fit."""
    raw, args, dims = _split_type(jtype)
    if dims:
        if not isinstance(value, list) or "<" in jtype:
            return None
        inner_type = raw + "[]" * (dims - 1)
        items = [_render_value(inner_type, v) for v in value]
        if any(i is None for i in items):
            return None
        return f"new {raw}{'[]' * dims}{{{', '.join(items)}}}"
    if raw in _LIST_TYPES | _SET_TYPES | _QUEUE_TYPES:
        if not isinstance(value, list):
            return None
        element = args[0] if args else "Integer"
        items = [_render_value(element, v) for v in value]
        if any(i is None for i in items):
            return None
        impl = {"LinkedList": "LinkedList", "TreeSet": "TreeSet", "SortedSet": "TreeSet", "LinkedHashSet": "LinkedHashSet"}.get(raw)
        if impl is None:
            impl = "HashSet" if raw in _SET_TYPES else "ArrayDeque" if raw in _QUEUE_TYPES else "ArrayList"
        return f"new java.util.{impl}<{element}>(java.util.Arrays.<{element}>asList({', '.join(items)}))"
    if raw in _INT_TYPES:
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        suffix = "L" if raw in ("long", "Long") else ""
        cast = f"({raw.lower()}) " if raw.lower() in ("short", "byte") else ""
        return f"{cast}{value}{suffix}"
    if raw in _FLOAT_TYPES:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return f"{float(value)}{'f' if raw.lower() == 'float' else ''}"
    if raw in ("boolean", "Boolean"):
        return ("true" if value else "false") if isinstance(value, bool) else None
    if raw in ("String", "CharSequence", "Object"):
        return json.dumps(value, ensure_ascii=True) if isinstance(value, str) else None
    if raw in ("char", "Character"):
        if isinstance(value, str) and len(value) == 1:
            return "'\\''" if value == "'" else "'\\\\'" if value == "\\" else f"'{value}'"
    return None
