"""Rewrite a C++ snippet so that running it prints an execution trace.

Edits are pure insertions (plus one move for `for` initializers), never
newlines, so every original statement stays on its original line; probes
carry the original 1-based line explicitly. The runtime they call lives in
include/cvt_runtime.hpp.

    statement            ->  cvt_rt::step(LINE); statement
    T x = ...;           ->  T x = ...; cvt_rt::Var CVTg1_("x", x, 1);
    while (c)            ->  while ((cvt_rt::step(LINE), (c)))
    for (int i = 0; c;)  ->  { int i = 0; <guard i> for (; (cvt_rt::step(LINE), (c));) ... }
    for (auto [a, b] : r) body -> for (...) { <guards a, b> cvt_rt::step(LINE); body }
    return e;            ->  return cvt_rt::ret(LINE, (e));
    f(params) { ...      ->  f(params) { cvt_rt::Frame ...; <param guards> cvt_rt::call(); ...
    struct S { ... }     ->  struct S { ... public: void CVTser_(cvt_rt::W&) const {...} ... }

Nothing here knows about algorithms; it only follows C++ syntax.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Node, Parser

_PARSER = Parser(Language(tscpp.language()))

RUNTIME_INCLUDE = '#include "cvt_runtime.hpp"\n'
ALLOC_FUNCS = {"malloc": "c_malloc", "calloc": "c_calloc", "realloc": "c_realloc", "free": "c_free"}
CLASS_NODES = {"class_specifier", "struct_specifier"}
OWN, GLOBAL = 1, 4
_KNOWN_TYPES = {"string", "size_t", "ll", "lld", "ull", "pii", "vi", "vll", "uint", "int64_t", "uint64_t", "int32_t"}

# LeetCode-style snippets use these without defining them (the judge does):
# (definition, serialized fields).
LEETCODE_TYPES = {
    "ListNode": (
        "struct ListNode { int val; ListNode* next; ListNode() : val(0), next(nullptr) {} "
        "ListNode(int x) : val(x), next(nullptr) {} ListNode(int x, ListNode* n) : val(x), next(n) {}",
        ["val", "next"],
    ),
    "TreeNode": (
        "struct TreeNode { int val; TreeNode* left; TreeNode* right; "
        "TreeNode() : val(0), left(nullptr), right(nullptr) {} "
        "TreeNode(int x) : val(x), left(nullptr), right(nullptr) {} "
        "TreeNode(int x, TreeNode* l, TreeNode* r) : val(x), left(l), right(r) {}",
        ["val", "left", "right"],
    ),
}


def serializer_members(name: str, fields: list[str], bases: list[str] = ()) -> str:
    writes = "".join(f"this->{b}::CVTser_(CVTw_); " for b in bases)
    writes += "".join(f'CVTw_.field("{f}", this->{f}); ' for f in fields)
    return (
        f" public: void CVTser_(cvt_rt::W& CVTw_) const {{ {writes}}} "
        f'static constexpr const char* CVTname_() {{ return "{name}"; }} '
    )


@dataclass
class ParamInfo:
    name: str
    base_type: str  # declared type without reference / pointer / array parts
    hint: str  # type as the driver sees it, e.g. "vector<int>&", "int[]"
    is_ref: bool = False
    pointer: int = 0
    array: bool = False


@dataclass
class FunctionInfo:
    name: str
    owner: str | None
    params: list[ParamInfo]
    line: int
    is_static: bool = False
    is_public: bool = True
    calls: set[str] = field(default_factory=set)


@dataclass
class Instrumented:
    source: str  # full translation unit to compile
    check_source: str  # the user's code with the same prelude, for error reports
    has_main: bool
    functions: list[FunctionInfo]
    used_leetcode_types: list[str]


@dataclass
class _Ctx:
    name: str
    is_main: bool = False
    is_void: bool = False
    ret_type: str | None = None  # usable return type text for `return {...}`
    in_case: bool = False


class Instrumenter:
    def __init__(self, code: str, skip_lines: frozenset[int] = frozenset()) -> None:
        self.code = code
        self.skip_lines = skip_lines  # leave constructs on these lines untraced
        self.src = code.encode("utf8")
        self.tree = _PARSER.parse(self.src)
        self.edits: list[tuple[int, int, int, str]] = []
        self.seq = 0
        self.uid = 0
        self.functions: list[FunctionInfo] = []
        self.has_main = False
        self.class_names = self._collect_class_names()
        self.called = self._collect_called_names(self.tree.root_node)

    # ------------------------------------------------------------ utilities

    def text(self, node: Node) -> str:
        return self.src[node.start_byte : node.end_byte].decode("utf8", "replace")

    @staticmethod
    def line(node: Node) -> int:
        return node.start_point[0] + 1

    def insert(self, pos: int, text: str) -> None:
        self.edits.append((pos, self.seq, pos, text))
        self.seq += 1

    def replace(self, start: int, end: int, text: str) -> None:
        self.edits.append((start, self.seq, end, text))
        self.seq += 1

    def fresh(self, prefix: str) -> str:
        self.uid += 1
        return f"CVT{prefix}{self.uid}_"

    def apply(self) -> str:
        out: list[bytes] = []
        cursor = 0
        for pos, _seq, end, text in sorted(self.edits, key=lambda e: (e[0], e[1])):
            if pos < cursor:
                continue  # overlaps an earlier replacement; drop it
            out.append(self.src[cursor:pos])
            out.append(text.encode("utf8"))
            cursor = max(cursor, end)
        out.append(self.src[cursor:])
        return b"".join(out).decode("utf8", "replace")

    def _collect_class_names(self) -> set[str]:
        names: set[str] = set()
        stack = [self.tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in CLASS_NODES:
                name = node.child_by_field_name("name")
                if name is not None and node.child_by_field_name("body") is not None:
                    names.add(self.text(name).split("::")[-1])
            stack.extend(node.children)
        return names

    def _collect_called_names(self, root: Node) -> set[str]:
        called: set[str] = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                fn = node.child_by_field_name("function")
                name = _callee_name(self, fn)
                if name:
                    called.add(name)
            stack.extend(node.children)
        return called

    # ------------------------------------------------------------ top level

    def run(self) -> None:
        self.top(self.tree.root_node)

    def top(self, node: Node) -> None:
        for child in node.named_children:
            kind = child.type
            if kind == "function_definition":
                self.function(child, owner=None, public=True)
            elif kind in CLASS_NODES:
                self.klass(child)
            elif kind == "template_declaration":
                self.top(child)
            elif kind == "declaration":
                self.global_declaration(child)
            elif kind in {"namespace_definition", "linkage_specification"}:
                body = child.child_by_field_name("body")
                if body is not None:
                    self.top(body)
            elif kind in {"declaration_list", "preproc_if", "preproc_ifdef", "preproc_else", "preproc_elif"}:
                self.top(child)

    def skipped(self, node: Node) -> bool:
        first, last = node.start_point[0] + 1, node.end_point[0] + 1
        return any(first <= line <= last for line in self.skip_lines)

    def global_declaration(self, decl: Node) -> None:
        type_node = decl.child_by_field_name("type")
        if type_node is not None and type_node.type in CLASS_NODES:
            self.klass(type_node)
        if _has_storage(self, decl, "extern") or _has_storage(self, decl, "typedef") or self.skipped(decl):
            return
        guards = self.guards_for(decl, GLOBAL, prefix="static ")
        if guards:
            self.insert(decl.end_byte, " " + guards)

    # ---------------------------------------------------------------- classes

    def klass(self, node: Node) -> None:
        body = node.child_by_field_name("body")
        if body is None:
            return
        name_node = node.child_by_field_name("name")
        name = self.text(name_node).split("::")[-1] if name_node is not None else "object"
        public = node.type == "struct_specifier"
        fields: list[str] = []
        for child in body.named_children:
            if child.type == "access_specifier":
                public = self.text(child).strip().startswith("public")
            elif child.type == "function_definition":
                self.function(child, owner=name, public=public)
            elif child.type == "template_declaration":
                for inner in child.named_children:
                    if inner.type == "function_definition":
                        self.function(inner, owner=name, public=public)
                    elif inner.type in CLASS_NODES:
                        self.klass(inner)
            elif child.type in CLASS_NODES:
                self.klass(child)
            elif child.type == "field_declaration":
                type_node = child.child_by_field_name("type")
                if type_node is not None and type_node.type in CLASS_NODES:
                    self.klass(type_node)
                if _has_storage(self, child, "static"):
                    continue
                for declarator in child.children_by_field_name("declarator"):
                    if _find(declarator, "function_declarator"):
                        continue
                    ident = _declared_name(self, declarator)
                    if ident:
                        fields.append(ident)
        bases = []
        clause = next((c for c in node.named_children if c.type == "base_class_clause"), None)
        if clause is not None:
            for base in clause.named_children:
                if base.type == "type_identifier" and self.text(base) in self.class_names:
                    bases.append(self.text(base))
        methods = [c for c in body.named_children if c.type in {"function_definition", "template_declaration"}]
        if not any(self.skipped(c) for c in body.named_children if c not in methods) or not self.skip_lines:
            self.insert(body.end_byte - 1, serializer_members(name, fields, bases))

    # -------------------------------------------------------------- functions

    def function(self, fn: Node, owner: str | None, public: bool) -> None:
        body = fn.child_by_field_name("body")
        declarator = fn.child_by_field_name("declarator")
        if body is None or body.type != "compound_statement" or declarator is None:
            return
        func_decl = _find(declarator, "function_declarator")
        if func_decl is None:
            return
        name_node = func_decl.child_by_field_name("declarator")
        if name_node is None or name_node.type in {"operator_name", "destructor_name"}:
            return
        full_name = self.text(name_node)
        if "operator" in full_name or "~" in full_name:
            return
        scope = None
        if name_node.type == "qualified_identifier":
            parts = full_name.replace(" ", "").split("::")
            scope, name = parts[-2] if len(parts) > 1 else None, parts[-1]
        else:
            name = full_name.split("<")[0]
        if name == (scope or owner):  # constructor
            return
        if any(self.text(c) in {"constexpr", "consteval"} for c in fn.children if c.type != "compound_statement"):
            return

        is_main = name == "main" and owner is None and scope is None
        type_node = fn.child_by_field_name("type")
        ret_text = self.text(type_node) if type_node is not None else ""
        returns_plain = declarator.type == "function_declarator"
        is_void = returns_plain and ret_text == "void"
        ret_type = ret_text if returns_plain and ret_text and "auto" not in ret_text else None
        if ret_type and any(self.text(c) == "const" for c in fn.children if c.type == "type_qualifier"):
            ret_type = "const " + ret_type
        is_static = _has_storage(self, fn, "static")

        params = self.params(func_decl.child_by_field_name("parameters"))
        info = FunctionInfo(
            name=name,
            owner=owner or scope,
            params=params,
            line=self.line(func_decl),
            is_static=is_static,
            is_public=public,
            calls=self._collect_called_names(body),
        )
        if is_main:
            self.has_main = True
        else:
            self.functions.append(info)

        if self.skipped(fn):
            return
        has_this = (owner is not None and not is_static) or (
            scope is not None and scope in self.class_names
        )
        self.instrument_body(
            body,
            _Ctx(name=name, is_main=is_main, is_void=is_void, ret_type=ret_type),
            line=self.line(func_decl),
            params=[] if is_main else params,
            has_this=has_this,
        )

    def params(self, plist: Node | None) -> list[ParamInfo]:
        result: list[ParamInfo] = []
        if plist is None:
            return result
        for p in plist.named_children:
            if p.type not in {"parameter_declaration", "optional_parameter_declaration"}:
                continue
            type_node = p.child_by_field_name("type")
            declarator = p.child_by_field_name("declarator")
            if type_node is None or declarator is None:
                continue
            name = _declared_name(self, declarator)
            if not name:
                continue
            is_ref = _find(declarator, "reference_declarator") is not None
            pointer = sum(1 for n in _walk(declarator) if n.type == "pointer_declarator")
            array = _find(declarator, "array_declarator") is not None
            base = self.text(type_node)
            hint = base + ("*" * pointer) + ("&" if is_ref else "") + ("[]" if array else "")
            result.append(ParamInfo(name, base, hint, is_ref, pointer, array))
        return result

    def instrument_body(
        self, body: Node, ctx: _Ctx, line: int, params: list[ParamInfo], has_this: bool
    ) -> None:
        name = ctx.name.replace('"', "")
        head = f'cvt_rt::Frame CVTf_("{name}", {line}, {"true" if ctx.is_main else "false"}); '
        for p in params:
            flags = 0 if p.is_ref else OWN
            head += f'cvt_rt::Var {self.fresh("p")}("{p.name}", {p.name}, {flags}); '
        if has_this:
            head += 'cvt_rt::Var CVTt_("this", *this, 0); '
        if not ctx.is_main:
            head += "cvt_rt::call(); "
        self.insert(body.start_byte + 1, " " + head)
        self.items(body, ctx, anchor=None)
        if not ctx.is_main and (ctx.is_void or ctx.ret_type is None):
            statements = [c for c in body.named_children if c.type != "comment"]
            last = self.line(statements[-1]) if statements else line
            self.insert(body.end_byte - 1, f" cvt_rt::retv({last}); ")

    def lambda_(self, node: Node, name: str) -> None:
        body = node.child_by_field_name("body")
        if body is None or body.type != "compound_statement" or self.skipped(node):
            return
        declarator = node.child_by_field_name("declarator")
        params: list[ParamInfo] = []
        ret_type = None
        is_void = False
        if declarator is not None:
            params = self.params(declarator.child_by_field_name("parameters"))
            trailing = next((c for c in declarator.named_children if c.type == "trailing_return_type"), None)
            if trailing is not None:
                ret_type = self.text(trailing).lstrip("-> ").strip()
                is_void = ret_type == "void"
        ctx = _Ctx(name=name, is_void=is_void, ret_type=ret_type if ret_type and "auto" not in ret_type else None)
        self.instrument_body(body, ctx, line=self.line(node), params=params, has_this=False)

    # ------------------------------------------------------------- statements

    def items(self, block: Node, ctx: _Ctx, anchor: int | None, in_case: bool = False) -> None:
        last_line = anchor
        for child in block.named_children:
            if child.type in {"comment", "attribute_declaration"}:
                continue
            if child.type == "case_statement":
                self.case(child, ctx)
                last_line = child.end_point[0] + 1
                continue
            probe = self.line(child) != last_line
            self.statement(child, ctx, probe, in_case=in_case)
            last_line = child.end_point[0] + 1

    def case(self, node: Node, ctx: _Ctx) -> None:
        value = node.child_by_field_name("value")
        last_line = None
        for child in node.named_children:
            if value is not None and child == value:
                continue
            if child.type == "comment":
                continue
            probe = self.line(child) != last_line
            self.statement(child, ctx, probe, in_case=True)
            last_line = child.end_point[0] + 1

    def body(self, node: Node | None, ctx: _Ctx, anchor: int | None, prefix: str = "") -> None:
        """A loop / if body: always braced so probes can be added inside."""
        if node is None:
            return
        if node.type == "compound_statement":
            if prefix:
                self.insert(node.start_byte + 1, " " + prefix)
            self.items(node, ctx, anchor)
            return
        self.insert(node.start_byte, "{ " + prefix)
        self.statement(node, ctx, probe=self.line(node) != anchor)
        self.insert(node.end_byte, " }")

    def probe(self, node: Node, line: int | None = None) -> None:
        self.insert(node.start_byte, f"cvt_rt::step({line or self.line(node)}); ")

    def hook(self, expr: Node, line: int) -> None:
        """Record a step each time a loop / else-if condition is evaluated."""
        self.insert(expr.start_byte, f"(cvt_rt::step({line}), (")
        self.expressions(expr, ctx=None)
        self.insert(expr.end_byte, "))")

    def statement(self, node: Node, ctx: _Ctx, probe: bool, in_case: bool = False) -> None:
        kind = node.type
        line = self.line(node)
        if kind == "compound_statement":
            self.items(node, ctx, anchor=None)
        elif kind in {"expression_statement", "break_statement", "continue_statement", "goto_statement", "throw_statement"}:
            if probe:
                self.probe(node)
            self.expressions(node, ctx)
        elif kind == "declaration":
            if probe:
                self.probe(node)
            self.expressions(node, ctx)
            if not in_case and not _has_storage(self, node, "extern"):
                flags = 0 if _has_storage(self, node, "static") else OWN
                guards = self.guards_for(node, flags)
                if guards:
                    self.insert(node.end_byte, " " + guards)
        elif kind == "return_statement":
            if probe:
                self.probe(node)
            self.return_(node, ctx)
        elif kind == "if_statement":
            if probe:
                self.probe(node)
            self.if_(node, ctx)
        elif kind == "for_statement":
            self.for_(node, ctx)
        elif kind == "for_range_loop":
            if probe:
                self.probe(node)
            self.range_for(node, ctx)
        elif kind == "while_statement":
            cond = node.child_by_field_name("condition")
            value = cond.child_by_field_name("value") if cond is not None else None
            if value is not None and value.type != "declaration" and cond.child_by_field_name("initializer") is None:
                self.hook(value, line)
            elif probe:
                self.probe(node)
            self.body(node.child_by_field_name("body"), ctx, anchor=line)
        elif kind == "do_statement":
            if probe:
                self.probe(node)
            self.body(node.child_by_field_name("body"), ctx, anchor=line)
            cond = node.child_by_field_name("condition")
            if cond is not None and cond.named_child_count == 1:
                self.hook(cond.named_children[0], self.line(cond))
        elif kind == "switch_statement":
            if probe:
                self.probe(node)
            cond = node.child_by_field_name("condition")
            if cond is not None:
                self.expressions(cond, ctx)
            body = node.child_by_field_name("body")
            if body is not None:
                self.items(body, ctx, anchor=line, in_case=True)
        elif kind == "labeled_statement":
            inner = node.named_children[-1] if node.named_children else None
            if inner is not None and inner.type != "statement_identifier":
                self.statement(inner, ctx, probe)
        elif kind == "try_statement":
            body = node.child_by_field_name("body")
            if body is not None:
                self.items(body, ctx, anchor=None)
            for clause in node.named_children:
                if clause.type == "catch_clause":
                    cbody = clause.child_by_field_name("body")
                    if cbody is not None:
                        self.items(cbody, ctx, anchor=None)
        # anything else (ERROR, preprocessor, empty `;`) is left untouched

    def if_(self, node: Node, ctx: _Ctx, else_if: bool = False) -> None:
        line = self.line(node)
        cond = node.child_by_field_name("condition")
        if cond is not None:
            value = cond.child_by_field_name("value")
            if else_if and value is not None and value.type != "declaration":
                self.hook(value, line)
            else:
                self.expressions(cond, ctx)
        self.body(node.child_by_field_name("consequence"), ctx, anchor=line)
        alt = node.child_by_field_name("alternative")
        if alt is None:
            return
        inner = alt.named_children[0] if alt.type == "else_clause" and alt.named_children else alt
        if inner.type == "if_statement":
            self.if_(inner, ctx, else_if=True)
        else:
            self.body(inner, ctx, anchor=line)

    def for_(self, node: Node, ctx: _Ctx) -> None:
        line = self.line(node)
        init = node.child_by_field_name("initializer")
        cond = node.child_by_field_name("condition")
        moved = False
        if init is not None and init.type == "declaration":
            guards = self.guards_for(init, OWN)
            if guards:
                self.insert(node.start_byte, "{ " + self.text(init) + " " + guards + " ")
                self.replace(init.start_byte, init.end_byte, ";")
                moved = True
        elif init is not None:
            self.expressions(init, ctx)
        if cond is not None:
            self.hook(cond, line)
        else:
            semis = [c for c in node.children if c.type == ";"]
            if semis:
                self.insert(semis[-1].start_byte, f"(cvt_rt::step({line}), true)")
        update = node.child_by_field_name("update")
        if update is not None:
            self.expressions(update, ctx)
        self.body(node.child_by_field_name("body"), ctx, anchor=line)
        if moved:
            self.insert(node.end_byte, " }")

    def range_for(self, node: Node, ctx: _Ctx) -> None:
        line = self.line(node)
        declarator = node.child_by_field_name("declarator")
        right = node.child_by_field_name("right")
        if right is not None:
            self.expressions(right, ctx)
        prefix = ""
        if declarator is not None:
            prefix = self.declarator_guards(declarator, OWN, "")
        self.body(node.child_by_field_name("body"), ctx, anchor=line, prefix=prefix + f"cvt_rt::step({line}); ")

    def return_(self, node: Node, ctx: _Ctx) -> None:
        line = self.line(node)
        value = next((c for c in node.named_children if c.type != "comment"), None)
        self.expressions(node, ctx)
        if ctx.is_main:
            return
        if value is None:
            self.insert(node.start_byte, f"cvt_rt::retv({line}); ")
            return
        keyword_end = node.children[0].end_byte
        if ctx.is_void:
            self.insert(keyword_end, " ((")
            self.insert(value.end_byte, f"), cvt_rt::retv({line}))")
        elif value.type == "identifier":
            self.insert(node.start_byte, f"cvt_rt::retval({line}, {self.text(value)}); ")
        elif value.type == "initializer_list":
            if ctx.ret_type:
                self.insert(value.start_byte, f"cvt_rt::ret({line}, {ctx.ret_type}")
                self.insert(value.end_byte, ")")
            else:
                self.insert(node.start_byte, f"cvt_rt::retv({line}); ")
        else:
            self.insert(value.start_byte, f"cvt_rt::ret({line}, (")
            self.insert(value.end_byte, "))")

    # ------------------------------------------------------------ expressions

    def expressions(self, node: Node, ctx: _Ctx | None, name: str | None = None) -> None:
        """Rewrite allocation calls and instrument named lambdas inside node."""
        for child in node.children:
            kind = child.type
            if kind == "lambda_expression":
                if name and name in self.called:
                    self.lambda_(child, name)
                continue  # anonymous lambdas (comparators, ...) run untraced
            if kind == "call_expression":
                fn = child.child_by_field_name("function")
                if fn is not None and fn.type == "identifier" and self.text(fn) in ALLOC_FUNCS:
                    self.replace(fn.start_byte, fn.end_byte, "cvt_rt::" + ALLOC_FUNCS[self.text(fn)])
            child_name = name
            if kind == "init_declarator":
                child_name = _declared_name(self, child.child_by_field_name("declarator"))
            elif kind == "assignment_expression":
                left = child.child_by_field_name("left")
                child_name = self.text(left) if left is not None and left.type == "identifier" else None
            self.expressions(child, ctx, child_name)

    # ------------------------------------------------------------------ guards

    def is_constructor_call(self, func_decl: Node) -> bool:
        """`T x(a, b);` parses like a function declaration; tell them apart.

        It is an object when every "parameter" is a lone identifier that is
        not a type we know of (a function declaration names types there).
        """
        params = func_decl.child_by_field_name("parameters")
        if params is None or params.named_child_count == 0:
            return False
        for p in params.named_children:
            if p.type != "parameter_declaration" or p.child_by_field_name("declarator") is not None:
                return False
            type_node = p.child_by_field_name("type")
            if type_node is None or type_node.type != "type_identifier":
                return False
            if self.text(type_node) in self.class_names or self.text(type_node) in _KNOWN_TYPES:
                return False
        return True

    def guards_for(self, decl: Node, flags: int, prefix: str = "") -> str:
        out = ""
        for declarator in decl.children_by_field_name("declarator"):
            target = declarator.child_by_field_name("declarator") if declarator.type == "init_declarator" else declarator
            if target is None:
                continue
            out += self.declarator_guards(target, flags, prefix)
        return out

    def declarator_guards(self, node: Node, flags: int, prefix: str) -> str:
        if node.type == "function_declarator" and self.is_constructor_call(node):
            node = node.child_by_field_name("declarator")  # `vector<int> dist(n, INT_MAX);`
        if _find(node, "function_declarator") is not None or _find(node, "qualified_identifier") is not None:
            return ""
        if node.type == "structured_binding_declarator" or _find(node, "structured_binding_declarator"):
            binding = node if node.type == "structured_binding_declarator" else _find(node, "structured_binding_declarator")
            return "".join(
                f'{prefix}cvt_rt::Var {self.fresh("g")}("{n}", {n}, {flags & GLOBAL}); '
                for n in (self.text(c) for c in binding.named_children if c.type == "identifier")
            )
        name = _declared_name(self, node)
        if not name:
            return ""
        if _find(node, "reference_declarator") is not None:
            flags &= ~OWN
        dims = _array_dims(node)
        guard = self.fresh("g")
        if dims == 1 and _find(node, "pointer_declarator") is None:
            return f'{prefix}cvt_rt::Arr {guard}("{name}", {name}, sizeof({name}) / sizeof(*{name}), {flags}); '
        if dims == 2 and _find(node, "pointer_declarator") is None:
            return (
                f'{prefix}cvt_rt::Arr2 {guard}("{name}", &{name}[0][0], sizeof({name}) / sizeof({name}[0]), '
                f"sizeof({name}[0]) / sizeof({name}[0][0]), {flags}); "
            )
        if dims > 2:
            return ""
        return f'{prefix}cvt_rt::Var {guard}("{name}", {name}, {flags}); '


# -------------------------------------------------------------------- helpers


def _walk(node: Node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.children)


def _find(node: Node | None, kind: str) -> Node | None:
    if node is None:
        return None
    for n in _walk(node):
        if n.type == kind:
            return n
    return None


def _has_storage(inst: Instrumenter, node: Node, word: str) -> bool:
    return any(
        c.type in {"storage_class_specifier", "type_qualifier"} and inst.text(c) == word
        for c in node.children
    ) or (word == "typedef" and inst.text(node).lstrip().startswith("typedef"))


def _declared_name(inst: Instrumenter, node: Node | None) -> str | None:
    """The identifier a (possibly nested) declarator declares."""
    while node is not None:
        if node.type in {"identifier", "field_identifier"}:
            return inst.text(node)
        if node.type in {"qualified_identifier", "function_declarator", "operator_name"}:
            return None
        inner = node.child_by_field_name("declarator")
        if inner is None:
            inner = next((c for c in node.named_children if c.type.endswith(("declarator", "identifier"))), None)
        node = inner
    return None


def _array_dims(node: Node) -> int:
    dims = 0
    while node is not None:
        if node.type == "array_declarator":
            dims += 1
        if node.type == "parenthesized_declarator":
            break  # pointer/reference to array: not an array variable
        inner = node.child_by_field_name("declarator")
        node = inner
    return dims


def _callee_name(inst: Instrumenter, fn: Node | None) -> str | None:
    if fn is None:
        return None
    if fn.type == "identifier":
        return inst.text(fn)
    if fn.type == "field_expression":
        field_node = fn.child_by_field_name("field")
        return inst.text(field_node) if field_node is not None else None
    if fn.type == "qualified_identifier":
        name = fn.child_by_field_name("name")
        return _callee_name(inst, name) if name is not None else None
    if fn.type == "template_function":
        name = fn.child_by_field_name("name")
        return inst.text(name) if name is not None else None
    return None


def instrument(code: str, skip_lines: frozenset[int] = frozenset()) -> Instrumented:
    inst = Instrumenter(code, skip_lines)
    inst.run()
    body = inst.apply()
    used = [t for t in LEETCODE_TYPES if t not in inst.class_names and _mentions(code, t)]
    judge = judge_prelude(code)
    traced_types = "".join(LEETCODE_TYPES[t][0] + serializer_members(t, LEETCODE_TYPES[t][1]) + "};\n" for t in used)
    plain_types = "".join(LEETCODE_TYPES[t][0] + " };\n" for t in used)
    return Instrumented(
        source=RUNTIME_INCLUDE + judge + traced_types + "#line 1\n" + body,
        check_source=judge + plain_types + "#line 1\n" + code,
        has_main=inst.has_main,
        functions=inst.functions,
        used_leetcode_types=used,
    )


def judge_prelude(code: str) -> str:
    """What an online judge adds around a snippet that has no #includes."""
    if re.search(r"^\s*#\s*include", code, re.M):
        return ""
    return "#include <bits/stdc++.h>\nusing namespace std;\n"


def _mentions(code: str, word: str) -> bool:
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", code, flags=re.S)
    return re.search(rf"\b{word}\b", stripped) is not None
