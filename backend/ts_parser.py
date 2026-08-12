"""Generic Tree-sitter parser for Java and JavaScript."""

from __future__ import annotations

import re
from typing import Any, Callable

from tree_sitter import Language, Node, Parser, Tree

from ir_analysis import enrich_ir

METHOD_NODE_TYPES = frozenset(
    {
        "method_declaration",
        "method_definition",
        "function_declaration",
        "function_definition",
        "function_item",
        "arrow_function",
    }
)
CLASS_NODE_TYPES = frozenset(
    {"class_declaration", "class_specifier", "class_definition"}
)


class TreeSitterParser:
    def __init__(self, code: str, language: str, language_module: Any) -> None:
        self.code = code
        self.language = language
        self.source = bytes(code, "utf8")
        self.parser = Parser(Language(language_module.language()))
        self.tree: Tree = self.parser.parse(self.source)
        self.root = self.tree.root_node

        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.global_variables: list[dict[str, Any]] = []
        self.conditions: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.loops: list[dict[str, Any]] = []
        self.arrays: list[dict[str, Any]] = []
        self.field_accesses: list[dict[str, Any]] = []
        self.subscript_accesses: list[dict[str, Any]] = []

        self._seen_conditions: set[str] = set()
        self._current_function: str | None = None
        self._current_class: str | None = None
        self._current_function_variables: list[dict[str, Any]] | None = None

    def parse(self) -> dict[str, Any]:
        self._walk(self.root)
        ir = {
            "language": self.language,
            "source_code": self.code,
            "functions": self.functions,
            "classes": self.classes,
            "global_variables": self.global_variables,
            "variables": self._collect_all_variables(),
            "conditions": self.conditions,
            "calls": self.calls,
            "loops": self.loops,
            "arrays": self.arrays,
            "field_accesses": self.field_accesses,
            "subscript_accesses": self.subscript_accesses,
            "data_structures": [],
            "algorithm": None,
            "operations": [],
        }
        return enrich_ir(ir, self.code, self.language)

    def _text(self, node: Node | None) -> str:
        if node is None:
            return ""
        return self.source[node.start_byte : node.end_byte].decode("utf8")

    def _line(self, node: Node) -> int:
        return node.start_point[0] + 1

    def _walk(self, node: Node) -> None:
        if node.type in CLASS_NODE_TYPES:
            self._parse_class(node)
            return

        if node.type in METHOD_NODE_TYPES:
            self._parse_method(node)
            return

        if node.type in ("if_statement", "if_expression"):
            self._parse_if(node)
        elif node.type in (
            "for_statement",
            "while_statement",
            "do_statement",
            "for_in_statement",
            "enhanced_for_statement",
        ):
            self._parse_loop(node)
        elif node.type in ("call_expression", "method_invocation", "new_expression"):
            self._parse_call(node)
        elif node.type in ("field_expression", "member_expression", "field_access"):
            self._parse_field_access(node)
        elif node.type in ("subscript_expression", "element_access_expression", "array_access"):
            self._parse_subscript(node)
        elif node.type in ("variable_declaration", "declaration", "local_variable_declaration"):
            self._parse_declaration(node)

        for child in node.children:
            self._walk(child)

    def _parse_class(self, node: Node) -> None:
        name_node = self._find_identifier(node)
        class_name = self._text(name_node) if name_node else "UnknownClass"
        members: list[dict[str, Any]] = []
        methods: list[dict[str, Any]] = []

        prev_class = self._current_class
        self._current_class = class_name

        body = self._find_class_body(node)
        if body:
            for child in body.children:
                if child.type in METHOD_NODE_TYPES:
                    method = self._parse_method_node(child, class_name)
                    if method:
                        self._walk_method_body(child, method)
                        methods.append(method)
                elif child.type in (
                    "field_declaration",
                    "declaration",
                    "public_field_definition",
                    "field_definition",
                ):
                    members.extend(self._parse_members(child))

        self._current_class = prev_class
        self.classes.append(
            {
                "name": class_name,
                "members": members,
                "methods": methods,
                "line": self._line(node),
            }
        )

    def _walk_method_body(self, node: Node, method: dict[str, Any]) -> None:
        body = self._find_body(node)
        if body is None:
            return

        prev_function = self._current_function
        fn_variables: list[dict[str, Any]] = []
        self._current_function = method["name"]
        self._current_function_variables = fn_variables

        condition_count = len(self.conditions)
        call_count = len(self.calls)
        loop_count = len(self.loops)

        for child in body.children:
            self._walk(child)

        method["conditions"] = self.conditions[condition_count:]
        method["calls"] = [c["function"] for c in self.calls[call_count:]]
        method["loops"] = self.loops[loop_count:]
        method["variables"] = fn_variables
        method["recursive"] = method["name"] in method["calls"]

        self._current_function = prev_function
        self._current_function_variables = None

    def _parse_method(self, node: Node) -> None:
        method = self._parse_method_node(node, self._current_class)
        if method and not self._current_class:
            self.functions.append(method)
        elif method and self._current_class:
            for cls in self.classes:
                if cls["name"] == self._current_class:
                    if not any(m["name"] == method["name"] for m in cls["methods"]):
                        cls["methods"].append(method)
                    break

        body = self._find_body(node)
        if body is None:
            return

        name = method["name"] if method else self._current_function
        if not name:
            return

        prev_function = self._current_function
        fn_variables: list[dict[str, Any]] = []
        self._current_function = name
        self._current_function_variables = fn_variables

        condition_count = len(self.conditions)
        call_count = len(self.calls)
        loop_count = len(self.loops)

        self._walk(body)

        if method:
            method["conditions"] = self.conditions[condition_count:]
            method["calls"] = [c["function"] for c in self.calls[call_count:]]
            method["loops"] = self.loops[loop_count:]
            method["variables"] = fn_variables
            method["recursive"] = name in method["calls"]

        self._current_function = prev_function
        self._current_function_variables = None

    def _parse_method_node(
        self, node: Node, class_name: str | None
    ) -> dict[str, Any] | None:
        name_node = self._find_method_name(node)
        if name_node is None:
            return None
        name = self._text(name_node)
        if name in {"if", "for", "while", "return", "class", "public", "private"}:
            return None

        return {
            "name": name,
            "class": class_name,
            "return_type": self._extract_return_type(node),
            "parameters": self._extract_parameters(node),
            "recursive": False,
            "conditions": [],
            "calls": [],
            "loops": [],
            "variables": [],
            "line": self._line(node),
        }

    def _find_method_name(self, node: Node) -> Node | None:
        seen_type = False
        for child in node.children:
            if child.type in (
                "void_type",
                "integral_type",
                "type_identifier",
                "generic_type",
                "primitive_type",
                "qualified_identifier",
                "template_type",
            ):
                seen_type = True
            elif child.type == "identifier" and seen_type:
                return child
            elif child.type == "function_declarator":
                for sub in child.children:
                    if sub.type in ("identifier", "field_identifier"):
                        return sub
        return self._find_identifier(node)

    def _parse_members(self, node: Node) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        text = self._text(node).strip().rstrip(";")
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            match = re.search(r"(\w+)\s*$", part)
            if match:
                members.append(
                    {
                        "name": match.group(1),
                        "type": part[: match.start(1)].strip() or "unknown",
                        "line": self._line(node),
                    }
                )
        return members

    def _parse_if(self, node: Node) -> None:
        for child in node.children:
            if child.type in (
                "parenthesized_expression",
                "condition_clause",
                "binary_expression",
                "identifier",
                "call_expression",
                "method_invocation",
            ):
                condition = self._text(child).strip("() ")
                if condition:
                    self._add_condition(condition)
                break

    def _add_condition(self, condition: str) -> None:
        normalized = re.sub(r"\s+", " ", condition.strip())
        if normalized and normalized not in self._seen_conditions:
            self._seen_conditions.add(normalized)
            self.conditions.append(normalized)

    def _parse_loop(self, node: Node) -> None:
        loop_type = node.type.replace("_statement", "").replace("_expression", "")
        info: dict[str, Any] = {
            "type": loop_type,
            "function": self._current_function,
            "line": self._line(node),
        }
        for child in node.children:
            if child.type in ("binary_expression", "condition_clause", "identifier"):
                info["condition"] = self._text(child).strip("() ")
                break
        self.loops.append(info)

    def _parse_call(self, node: Node) -> None:
        name = self._extract_call_name(node)
        if not name:
            return
        arguments = self._extract_call_arguments(node)
        self.calls.append(
            {
                "function": name,
                "arguments": arguments,
                "caller": self._current_function,
                "line": self._line(node),
            }
        )

    def _extract_call_name(self, node: Node) -> str:
        if node.type == "method_invocation":
            for child in reversed(node.children):
                if child.type == "identifier":
                    return self._text(child)
        if node.type == "call_expression":
            fn = node.children[0] if node.children else None
            if fn is None:
                return ""
            text = self._text(fn)
            return text.split(".")[-1] if "." in text else text
        if node.type == "new_expression":
            for child in node.children:
                if child.type in ("type_identifier", "identifier", "generic_type"):
                    return f"new_{self._text(child)}"
        return ""

    def _extract_call_arguments(self, node: Node) -> list[str]:
        args: list[str] = []
        for child in node.children:
            if child.type in ("argument_list", "arguments"):
                for arg in child.children:
                    if arg.type not in ("(", ")", ","):
                        args.append(self._text(arg).strip())
        return args

    def _parse_field_access(self, node: Node) -> None:
        text = self._text(node).strip()
        if not text:
            return
        parts = text.split(".")
        self.field_accesses.append(
            {
                "object": parts[0] if parts else text,
                "field": parts[-1] if len(parts) > 1 else "",
                "expression": text,
                "function": self._current_function,
                "line": self._line(node),
            }
        )

    def _parse_subscript(self, node: Node) -> None:
        if not node.children:
            return
        array_expr = self._text(node.children[0]).strip()
        index_expr = ""
        for child in node.children[1:]:
            if child.type not in ("[", "]", "subscript_argument_list"):
                index_expr = self._text(child).strip("[] ")
                break
            for sub in child.children:
                if sub.type not in ("[", "]"):
                    index_expr = self._text(sub).strip()
                    break
        self.subscript_accesses.append(
            {
                "array": array_expr,
                "index": index_expr,
                "expression": self._text(node).strip(),
                "function": self._current_function,
                "line": self._line(node),
            }
        )

    def _parse_declaration(self, node: Node) -> None:
        text = self._text(node).strip()
        if not text:
            return
        match = re.findall(r"\b(\w+)\s*=", text)
        for name in match:
            var = {
                "name": name,
                "type": "unknown",
                "scope": "local" if self._current_function else "global",
                "line": self._line(node),
            }
            if self._current_function_variables is not None:
                self._current_function_variables.append(var)
            elif not self._current_function:
                self.global_variables.append(var)

    def _find_identifier(self, node: Node) -> Node | None:
        skip = {"class", "public", "private", "protected", "static", "void", "int", "async"}
        for child in node.children:
            if child.type == "identifier":
                text = self._text(child)
                if text not in skip:
                    return child
            if child.type in ("type_identifier", "property_identifier"):
                return child
            found = self._find_identifier(child)
            if found is not None and self._text(found) not in skip:
                return found
        return None

    def _find_class_body(self, node: Node) -> Node | None:
        for child in node.children:
            if child.type in ("class_body", "declaration_list", "field_declaration_list"):
                return child
        return None

    def _find_body(self, node: Node) -> Node | None:
        for child in node.children:
            if child.type in ("block", "compound_statement", "statement_block", "class_body"):
                return child
        return None

    def _extract_return_type(self, node: Node) -> str:
        for child in node.children:
            if child.type in (
                "void_type",
                "integral_type",
                "type_identifier",
                "generic_type",
                "primitive_type",
            ):
                return self._text(child).strip()
        return "void"

    def _extract_parameters(self, node: Node) -> list[dict[str, str]]:
        params: list[dict[str, str]] = []
        for child in node.children:
            if child.type in (
                "formal_parameters",
                "parameter_list",
                "parameters",
            ):
                for param in child.children:
                    if param.type in (
                        "formal_parameter",
                        "parameter",
                        "required_parameter",
                        "optional_parameter",
                    ):
                        name_node = self._find_identifier(param)
                        ptype = self._text(param).strip()
                        pname = self._text(name_node) if name_node else ""
                        if pname:
                            ptype = ptype.replace(pname, "").strip()
                        params.append({"name": pname or "arg", "type": ptype or "any"})
        return params

    def _collect_all_variables(self) -> list[dict[str, Any]]:
        variables = list(self.global_variables)
        for fn in self.functions:
            variables.extend(fn.get("variables", []))
        for cls in self.classes:
            for method in cls.get("methods", []):
                variables.extend(method.get("variables", []))
        return variables


def parse_with_tree_sitter(code: str, language: str, language_module: Any) -> dict[str, Any]:
    return TreeSitterParser(code, language, language_module).parse()
