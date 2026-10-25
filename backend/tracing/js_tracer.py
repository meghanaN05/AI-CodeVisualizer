"""Trace JavaScript snippets by source instrumentation, run under Node.

Why instrumentation rather than the inspector protocol: stepping with
`node --inspect` pauses at every V8 break location (several per statement,
plus builtins), needs a CDP round trip per scope and per object, and reports
let/const in their dead zone ambiguously. Rewriting the source instead gives
exactly one probe per statement, reads variables through closures placed at
the probe (so scoping is the engine's own), and runs at near-native speed.

The snippet is parsed with tree-sitter-javascript and only *insertions* are
made, so every probe carries the line number of the ORIGINAL snippet:

    ;__T.s(id, getter);            before each statement            -> "line"
    (__T.s(id, getter), test)      in for/while/do-while tests      -> "line" per iteration
    const __f$=__T.c(id, getter);  at function entry                -> "call"
    try { body } finally { __T.l(__f$) }                            -> implicit "return"
    return __T.r(id, expr)                                          -> "return"

`getter(k)` is `($$k) => { switch ($$k) { case 0: return i; ... } }`: the names
lexically declared in the frame's function up to that point in the scope
chain (plus closed-over variables of enclosing functions). The runtime
(tracing/js/runtime.js) calls it per name and skips names in the temporal
dead zone, functions and undefined.
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter_javascript
from tree_sitter import Language, Node, Parser

from tracing.driver import DriverPlan, Param, synthesize_args
from tracing.python_tracer import _has_user_calls, _mutates_array_arg
from tracing.sandbox import SandboxResult, parse_trace_output, run_sandboxed

RUNTIME = Path(__file__).resolve().parent / "js" / "runtime.js"
MAX_STEPS = 1500
NODE_FLAGS = ["--max-old-space-size=512", "--stack-size=2000"]

_PARSER = Parser(Language(tree_sitter_javascript.language()))

FUNCTION_TYPES = {
    "function_declaration",
    "generator_function_declaration",
    "function_expression",
    "function",
    "generator_function",
    "arrow_function",
    "method_definition",
}
BLOCK_SCOPE_TYPES = {"statement_block", "for_statement", "for_in_statement", "catch_clause", "switch_body"}
NO_PROBE_TYPES = {"statement_block", "empty_statement", "comment", "import_statement", "export_statement"}


def trace_javascript(code: str) -> dict[str, Any]:
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
    node = _node_binary()
    if node is None:
        return {"language": "javascript", "steps": [], "error": "Node.js is not installed", "truncated": False}
    try:
        instrumented, sites = instrument(code)
    except RecursionError:
        instrumented, sites = "throw new Error('snippet too deeply nested to trace')", []
    request = {"original": code, "instrumented": instrumented, "sites": sites, "max_steps": MAX_STEPS}
    result: SandboxResult = run_sandboxed([node, *NODE_FLAGS, str(RUNTIME)], stdin=json.dumps(request))
    if result.returncode < 0 and not result.timed_out and not result.stdout.strip():
        # Killed by a signal (SIGXCPU from the CPU limit, or OOM) before the
        # runtime could print: a hot loop inside one statement or a builtin.
        return {"language": "javascript", "steps": [], "truncated": False,
                "error": "Execution exceeded the CPU or memory limit"}
    return parse_trace_output(result, "javascript")


@functools.lru_cache(maxsize=1)
def _node_binary() -> str | None:
    """Absolute path of the real node executable.

    `node` on PATH is often a version-manager shim (asdf, nvm, volta) that
    needs the user's environment, which the sandbox deliberately strips.
    """
    node = os.environ.get("NODE_BINARY") or shutil.which("node")
    if node is None:
        return None
    try:
        probe = subprocess.run(
            [node, "-e", "process.stdout.write(process.execPath)"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    path = probe.stdout.strip()
    return path if probe.returncode == 0 and path else None


# ------------------------------------------------------------ instrumentation


@dataclass
class Scope:
    kind: str  # "module" | "function" | "block"
    parent: Scope | None
    names: list[str] = field(default_factory=list)
    fn: Scope | None = None  # owning function (or module) scope
    declared: set[str] = field(default_factory=set)  # every name declared in this function
    free: list[str] = field(default_factory=list)  # closed-over names of enclosing functions

    def declare(self, name: str) -> None:
        if name not in self.names:
            self.names.append(name)
        (self.fn or self).declared.add(name)


@dataclass
class _Insert:
    pos: int
    closer: bool
    order: float
    text: str


def instrument(code: str) -> tuple[str, list[dict[str, Any]]]:
    """Return (instrumented source, probe sites)."""
    source = code.encode("utf8")
    tree = _PARSER.parse(source)
    return _Instrumenter(source).run(tree.root_node)


class _Instrumenter:
    def __init__(self, source: bytes) -> None:
        self.src = source
        self.scopes: dict[int, Scope] = {}
        self.inserts: list[_Insert] = []
        self.sites: list[dict[str, Any]] = []
        self.functions: list[tuple[Node, Scope]] = []

    def run(self, root: Node) -> tuple[str, list[dict[str, Any]]]:
        module = Scope("module", None)
        module.fn = module
        self.scopes[root.id] = module
        for child in root.named_children:
            self._collect(child, module)
        for node, fscope in self.functions:
            self._resolve_free(node, fscope)
        self._visit_list(root, module, skip_directives=True)

        # Closers before openers at the same spot; inner closers first,
        # outer openers first.
        self.inserts.sort(key=lambda e: (e.pos, not e.closer, e.order))
        out, last = [], 0
        for ins in self.inserts:
            out.append(self.src[last : ins.pos])
            out.append(ins.text.encode("utf8"))
            last = ins.pos
        out.append(self.src[last:])
        return b"".join(out).decode("utf8"), self.sites

    # -- pass 1: declarations per scope

    def _collect(self, node: Node, scope: Scope) -> None:
        t = node.type
        if t in FUNCTION_TYPES:
            fscope = Scope("function", scope)
            fscope.fn = fscope
            self.scopes[node.id] = fscope
            if t == "method_definition":
                fscope.declare("this")
            for param in self._params(node):
                for name in _pattern_names(param):
                    fscope.declare(name)
            body = node.child_by_field_name("body")
            if body is not None:
                if body.type == "statement_block":
                    self.scopes[body.id] = fscope
                    for child in body.named_children:
                        self._collect(child, fscope)
                else:
                    self._collect(body, fscope)
            self.functions.append((node, fscope))
            return
        if t in BLOCK_SCOPE_TYPES:
            block = Scope("block", scope, fn=scope.fn)
            self.scopes[node.id] = block
            if t == "for_in_statement":
                kind = _decl_kind(node)
                left = node.child_by_field_name("left")
                if kind and left is not None:
                    target = scope.fn if kind == "var" else block
                    for name in _pattern_names(left):
                        target.declare(name)
            elif t == "catch_clause":
                param = node.child_by_field_name("parameter")
                if param is not None:
                    for name in _pattern_names(param):
                        block.declare(name)
            for child in node.named_children:
                self._collect(child, block)
            return
        if t in {"lexical_declaration", "variable_declaration"}:
            target = scope if t == "lexical_declaration" else scope.fn
            for decl in node.named_children:
                if decl.type == "variable_declarator":
                    name = decl.child_by_field_name("name")
                    if name is not None:
                        for n in _pattern_names(name):
                            target.declare(n)
        for child in node.named_children:
            self._collect(child, scope)

    def _resolve_free(self, node: Node, fscope: Scope) -> None:
        """Names this function reads from enclosing (non-module) functions."""
        seen: set[str] = set()
        for name in _identifiers(node, self.src):
            if name in seen or name in fscope.declared:
                continue
            seen.add(name)
            scope = fscope.parent
            while scope is not None and scope.fn is not None and scope.fn.kind == "function":
                if name in scope.names:
                    fscope.free.append(name)
                    break
                scope = scope.parent

    # -- pass 2: probes

    def _visible(self, scope: Scope) -> list[str]:
        chain = []
        s: Scope | None = scope
        while s is not None:
            chain.append(s)
            if s is s.fn:
                break
            s = s.parent
        names: list[str] = []
        for s in reversed(chain):  # outer first, like declaration order
            for name in s.names:
                if name not in names:
                    names.append(name)
        fn = scope.fn or scope
        names.extend(n for n in fn.free if n not in names)
        return [n for n in names if n != "arguments"]

    def _site(self, line: int, scope: Scope, func: str | None = None) -> int:
        site: dict[str, Any] = {"line": line, "names": self._visible(scope)}
        if func is not None:
            site["func"] = func
        self.sites.append(site)
        return len(self.sites) - 1

    def _getter(self, site_id: int) -> str:
        names = self.sites[site_id]["names"]
        if not names:
            return "null"
        cases = "".join(f"case {i}:return {name};" for i, name in enumerate(names))
        return f"($$k)=>{{switch($$k){{{cases}}}}}"

    def _probe(self, line: int, scope: Scope, quiet: bool = False) -> str:
        site = self._site(line, scope)
        if quiet:
            self.sites[site]["quiet"] = True
        return f"__T.s({site},{self._getter(site)})"

    def _insert(self, pos: int, text: str, order: float, closer: bool = False) -> None:
        self.inserts.append(_Insert(pos, closer, -order if closer else order, text))

    def _scope(self, node: Node, scope: Scope) -> Scope:
        return self.scopes.get(node.id, scope)

    def _visit_list(self, node: Node, scope: Scope, skip_directives: bool = False) -> None:
        directives = skip_directives
        for child in node.named_children:
            if directives and _is_directive(child):
                continue
            directives = False
            if child.type not in NO_PROBE_TYPES:
                depth = _depth(child)
                self._insert(child.start_byte, f";{self._probe(_line(child), scope)};", depth)
            self._visit(child, scope)

    def _visit_single(self, stmt: Node | None, scope: Scope, iteration: str | None = None) -> None:
        """A statement in a body position (if/loop body): wrap it in a block."""
        if stmt is None:
            return
        depth = _depth(stmt)
        if stmt.type == "statement_block":
            if iteration:
                self._insert(stmt.start_byte + 1, f";{iteration};", depth - 0.5)
            self._visit(stmt, scope)
            return
        self._insert(stmt.start_byte, "{", depth - 0.9)
        if iteration:
            self._insert(stmt.start_byte, f";{iteration};", depth - 0.5)
        if stmt.type not in NO_PROBE_TYPES:
            self._insert(stmt.start_byte, f";{self._probe(_line(stmt), scope)};", depth)
        self._visit(stmt, scope)
        self._insert(stmt.end_byte, "}", depth, closer=True)

    def _visit(self, node: Node, scope: Scope) -> None:
        t = node.type
        scope = self._scope(node, scope)
        if t in FUNCTION_TYPES:
            self._visit_function(node, scope)
        elif t in {"program", "statement_block"}:
            self._visit_list(node, scope)
        elif t in {"switch_case", "switch_default"}:
            value = node.child_by_field_name("value")
            if value is not None:
                self._visit(value, scope)
            body = [c for c in node.children_by_field_name("body")]
            for child in body:
                if child.type not in NO_PROBE_TYPES:
                    self._insert(child.start_byte, f";{self._probe(_line(child), scope)};", _depth(child))
                self._visit(child, scope)
        elif t == "if_statement":
            self._visit_field(node, "condition", scope)
            self._visit_single(node.child_by_field_name("consequence"), scope)
            alt = node.child_by_field_name("alternative")
            if alt is not None:
                inner = [c for c in alt.named_children if c.type != "comment"]
                self._visit_single(inner[0] if inner else None, scope)
        elif t == "for_statement":
            self._visit_field(node, "initializer", scope)
            cond = node.child_by_field_name("condition")
            line, order = _line(node), _depth(node) + 0.5
            quiet = _body_on_line(node, line)
            expr = cond
            if cond is not None and cond.type == "expression_statement":
                expr = cond.named_children[0] if cond.named_children else None
            elif cond is not None and cond.type == "empty_statement":
                expr = None
            if expr is not None:
                self._insert(expr.start_byte, f"({self._probe(line, scope, quiet)},", order)
                self._visit(expr, scope)
                self._insert(expr.end_byte, ")", order, closer=True)
            elif cond is not None:  # for (init;; update)
                self._insert(cond.start_byte, f"({self._probe(line, scope, quiet)},true)", order)
            self._visit_field(node, "increment", scope)
            self._visit_single(node.child_by_field_name("body"), scope)
        elif t == "for_in_statement":
            self._visit_field(node, "left", scope)
            self._visit_field(node, "right", scope)
            iteration = self._probe(_line(node), scope, _body_on_line(node, _line(node)))
            self._visit_single(node.child_by_field_name("body"), scope, iteration)
        elif t == "while_statement":
            self._probe_condition(node, scope)
            self._visit_single(node.child_by_field_name("body"), scope)
        elif t == "do_statement":
            self._visit_single(node.child_by_field_name("body"), scope)
            self._probe_condition(node, scope)
        elif t == "labeled_statement":
            # `label: loop` must stay adjacent; the label already got a probe.
            self._visit_field(node, "body", scope)
        elif t == "return_statement":
            self._visit_return(node, scope)
        else:
            for child in node.named_children:
                self._visit(child, scope)

    def _visit_field(self, node: Node, name: str, scope: Scope) -> None:
        child = node.child_by_field_name(name)
        if child is not None:
            self._visit(child, scope)

    def _probe_condition(self, node: Node, scope: Scope) -> None:
        cond = node.child_by_field_name("condition")
        if cond is None:
            return
        if cond.type == "parenthesized_expression":
            quiet = node.type == "while_statement" and _body_on_line(node, _line(cond))
            self._insert(cond.start_byte + 1, f"{self._probe(_line(cond), scope, quiet)},", _depth(node) + 0.5)
        self._visit(cond, scope)

    def _visit_return(self, node: Node, scope: Scope) -> None:
        fn = scope.fn
        values = [c for c in node.named_children if c.type != "comment"]
        if fn is None or fn.kind != "function":
            for v in values:
                self._visit(v, scope)
            return
        site = self._site(_line(node), scope)
        order = _depth(node) + 0.5
        if values:
            expr = values[0]
            self._insert(expr.start_byte, f"__T.r({site},", order)
            self._visit(expr, scope)
            self._insert(expr.end_byte, ")", order, closer=True)
        else:
            keyword = node.children[0]
            self._insert(keyword.end_byte, f" __T.r({site},undefined)", order)

    def _visit_function(self, node: Node, fscope: Scope) -> None:
        body = node.child_by_field_name("body")
        if body is None:
            return
        if _is_async_or_generator(node):
            # A suspended generator/async frame would corrupt the shadow
            # stack; these run untraced (calls into normal functions still trace).
            self._visit_untraced(body, fscope)
            return
        name = _function_name(node, self.src)
        site = self._site(_line(node), fscope, func=name)
        enter = f"const __f$=__T.c({site},{self._getter(site)});try{{"
        leave = "}finally{__T.l(__f$)}"
        order = _depth(node)
        if body.type == "statement_block":
            stmts = body.named_children
            pos = body.start_byte + 1
            for child in stmts:
                if _is_directive(child):
                    pos = child.end_byte
                elif child.type != "comment":
                    break
            if pos == body.end_byte - 1:  # empty body: one insertion keeps the order
                self._insert(pos, enter + leave, order)
                return
            self._insert(pos, enter, order)
            self._visit_list(body, fscope, skip_directives=True)
            self._insert(body.end_byte - 1, leave, order, closer=True)
        else:
            ret = self._site(_line(body), fscope)
            line_probe = self._probe(_line(body), fscope)
            self._insert(body.start_byte, f"{{{enter}{line_probe};return __T.r({ret},", order)
            self._visit(body, fscope)
            self._insert(body.end_byte, f"){leave}}}", order, closer=True)

    def _visit_untraced(self, node: Node, scope: Scope) -> None:
        for child in node.named_children:
            if child.type in FUNCTION_TYPES:
                self._visit(child, self._scope(child, scope))
            else:
                self._visit_untraced(child, scope)

    @staticmethod
    def _params(node: Node) -> list[Node]:
        params = node.child_by_field_name("parameters")
        if params is not None:
            return [p for p in params.named_children if p.type != "comment"]
        single = node.child_by_field_name("parameter")
        return [single] if single is not None else []


def _line(node: Node) -> int:
    return node.start_point[0] + 1


def _body_on_line(loop: Node, line: int) -> bool:
    """Does the loop body's first statement sit on the loop header's line?

    Then the header probe (which runs after the update, `i++`) must not record
    a step: the body's own probe shows the iteration with the right values.
    """
    body = loop.child_by_field_name("body")
    if body is None:
        return False
    if body.type == "statement_block":
        stmts = [c for c in body.named_children if c.type != "comment"]
        if not stmts:
            return False
        body = stmts[0]
    return _line(body) == line


def _depth(node: Node) -> int:
    depth = 0
    parent = node.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf8")


def _is_directive(node: Node) -> bool:
    return (
        node.type == "expression_statement"
        and node.named_child_count >= 1
        and node.named_children[0].type == "string"
    )


def _decl_kind(node: Node) -> str | None:
    for child in node.children:
        if child.type in {"var", "let", "const"}:
            return child.type
    return None


def _is_async_or_generator(node: Node) -> bool:
    if node.type in {"generator_function", "generator_function_declaration"}:
        return True
    return any(c.type in {"async", "*"} for c in node.children)


def _pattern_names(node: Node) -> list[str]:
    t = node.type
    if t in {"identifier", "shorthand_property_identifier_pattern"}:
        return [node.text.decode("utf8")]
    if t in {"assignment_pattern", "object_assignment_pattern"}:
        left = node.child_by_field_name("left")
        return _pattern_names(left) if left is not None else []
    if t == "pair_pattern":
        value = node.child_by_field_name("value")
        return _pattern_names(value) if value is not None else []
    if t in {"object_pattern", "array_pattern", "rest_pattern"}:
        return [n for c in node.named_children for n in _pattern_names(c)]
    return []


def _identifiers(node: Node, src: bytes) -> list[str]:
    found: list[str] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in {"identifier", "shorthand_property_identifier"}:
            found.append(_text(n, src))
        stack.extend(reversed(n.named_children))
    return found


def _function_name(node: Node, src: bytes) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return _text(name, src)
    parent = node.parent
    while parent is not None and parent.type == "parenthesized_expression":
        parent = parent.parent
    if parent is None:
        return "<anonymous>"
    if parent.type == "variable_declarator":
        target = parent.child_by_field_name("name")
    elif parent.type in {"assignment_expression", "augmented_assignment_expression"}:
        target = parent.child_by_field_name("left")
        if target is not None and target.type == "member_expression":
            target = target.child_by_field_name("property")
    elif parent.type == "pair":
        target = parent.child_by_field_name("key")
    elif parent.type == "field_definition":
        target = parent.child_by_field_name("property")
    else:
        target = None
    if target is None or target.type not in {
        "identifier", "property_identifier", "private_property_identifier", "string", "number",
    }:
        return "<anonymous>"
    return _text(target, src).strip("'\"")


# ------------------------------------------------------------------- driver

_JSDOC_PARAM = re.compile(r"@param\s+\{([^}]*)\}\s+\[?([A-Za-z_$][\w$]*)")


def _plan_driver(code: str, variant: str) -> DriverPlan | None:
    """Pick the snippet's entry function and example arguments for it."""
    src = code.encode("utf8")
    root = _PARSER.parse(src).root_node
    if root.has_error:
        return None

    # (owner class, name, function node, statement carrying the JSDoc)
    candidates: list[tuple[str | None, str, Node, Node]] = []
    for stmt in root.named_children:
        decl = stmt
        if stmt.type == "export_statement":
            decl = stmt.child_by_field_name("declaration") or stmt
        if decl.type == "function_declaration":
            candidates.append((None, _function_name(decl, src), decl, stmt))
        elif decl.type in {"lexical_declaration", "variable_declaration"}:
            for d in decl.named_children:
                value = d.child_by_field_name("value") if d.type == "variable_declarator" else None
                name = d.child_by_field_name("name") if value is not None else None
                if value is not None and value.type in {"arrow_function", "function_expression", "function"} \
                        and name is not None and name.type == "identifier" and not _is_async_or_generator(value):
                    candidates.append((None, _text(name, src), value, stmt))
        elif decl.type == "class_declaration":
            cls = decl.child_by_field_name("name")
            body = decl.child_by_field_name("body")
            if cls is None or body is None:
                continue
            for member in body.named_children:
                if member.type != "method_definition" or _is_async_or_generator(member):
                    continue
                if any(c.type in {"static", "get", "set"} for c in member.children):
                    continue
                method = _function_name(member, src)
                if method == "constructor" or method.startswith(("_", "#")):
                    continue
                candidates.append((_text(cls, src), method, member, member))

    # The entry point is the function no other function calls; with several,
    # take the last one defined (helpers are usually written first).
    called = set()
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None and fn.type == "member_expression":
                fn = fn.child_by_field_name("property")
            if fn is not None and fn.type in {"identifier", "property_identifier"}:
                called.add(_text(fn, src))
        stack.extend(n.named_children)
    entries = [c for c in candidates if c[1] not in called] or candidates

    for owner, name, fn, doc_anchor in reversed(entries):
        params = _driver_params(fn, doc_anchor, src)
        if params is None:
            continue
        args = synthesize_args(params, variant)
        if args is not None:
            return DriverPlan(function=name, owner_class=owner, args=args, variant=variant)
    return None


def _driver_params(fn: Node, doc_anchor: Node, src: bytes) -> list[Param] | None:
    """Required positional parameters, typed from JSDoc when present."""
    hints = _jsdoc_types(doc_anchor, src)
    params: list[Param] = []
    for p in _Instrumenter._params(fn):
        if p.type == "identifier":
            name = _text(p, src)
            params.append(Param(name, hints.get(name, "")))
        elif p.type in {"assignment_pattern", "rest_pattern"}:
            break  # optional from here on: let the defaults apply
        else:
            return None  # destructured parameter: no generic example value
    return params


def _jsdoc_types(node: Node, src: bytes) -> dict[str, str]:
    comment = node.prev_named_sibling
    if comment is None or comment.type != "comment":
        return {}
    text = _text(comment, src)
    if not text.startswith("/**"):
        return {}
    return {name: _js_type_hint(type_) for type_, name in _JSDOC_PARAM.findall(text)}


def _js_type_hint(jsdoc_type: str) -> str:
    """Map JSDoc types onto the hint vocabulary driver.synthesize_args knows."""
    t = jsdoc_type.strip().replace(" ", "")
    t = re.sub(r"Array<([^<>]*)>", r"\1[]", t)
    lowered = t.lower()
    if lowered.startswith("character") or lowered.startswith("char"):
        return "char" + t[t.find("["):] if "[" in t else "char"
    if lowered.startswith("string"):
        return "str" + t[len("string"):]
    return t


def _render_call(driver: DriverPlan) -> str:
    args = ", ".join(json.dumps(value) for _name, value in driver.args)
    target = f"new {driver.owner_class}().{driver.function}" if driver.owner_class else driver.function
    return f"\n\n;{target}({args});\n"
