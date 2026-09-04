"""C++ parser using Tree-sitter — extracts AST features into IR."""

from __future__ import annotations

import re
from typing import Any

import tree_sitter_cpp as tscpp
from ir_analysis import enrich_ir
from tree_sitter import Language, Node, Parser, Tree

_CPP_LANGUAGE = Language(tscpp.language())
_PARSER = Parser(_CPP_LANGUAGE)

TREE_POINTER_FIELDS = frozenset({"left", "right", "parent", "data", "val", "value"})
GRAPH_HINTS = frozenset(
    {
        "adjacency",
        "adj",
        "graph",
        "edges",
        "vertices",
        "neighbors",
        "neighbour",
    }
)
LINKED_LIST_FIELDS = frozenset({"next", "prev", "head", "tail"})


class CppParser:
    def __init__(self, code: str) -> None:
        self.code = code
        self.source = bytes(code, "utf8")
        self.tree: Tree = _PARSER.parse(self.source)
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
        for child in self.root.children:
            if child.type == "class_specifier":
                self._parse_class(child)
            elif child.type == "function_definition":
                self._parse_function(child)
            elif child.type == "declaration":
                self._parse_global_declaration(child)
            else:
                self._walk(child)

        ir = {
            "language": "cpp",
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
            "data_structures": self._detect_data_structures(),
            "algorithm": self._detect_algorithm(self._detect_data_structures()),
            "operations": self._derive_operations(
                self._detect_data_structures(),
                self._detect_algorithm(self._detect_data_structures()),
            ),
        }
        return enrich_ir(ir, self.code, "cpp")

    def _text(self, node: Node | None) -> str:
        if node is None:
            return ""
        return self.source[node.start_byte : node.end_byte].decode("utf8")

    def _line(self, node: Node) -> int:
        return node.start_point[0] + 1

    def _find_child(self, node: Node, node_type: str) -> Node | None:
        for child in node.children:
            if child.type == node_type:
                return child
        return None

    def _find_children(self, node: Node, node_type: str) -> list[Node]:
        return [child for child in node.children if child.type == node_type]

    def _walk(self, node: Node) -> None:
        if node.type == "if_statement":
            self._parse_if(node)
        elif node.type in ("for_statement", "while_statement", "do_statement"):
            self._parse_loop(node)
        elif node.type == "call_expression":
            self._parse_call(node)
        elif node.type == "field_expression":
            self._parse_field_access(node)
        elif node.type == "subscript_expression":
            self._parse_subscript(node)
        elif node.type == "declaration":
            self._parse_local_declaration(node)

        for child in node.children:
            self._walk(child)

    def _parse_class(self, node: Node) -> None:
        name_node = self._find_child(node, "type_identifier")
        if name_node is None:
            name_node = self._find_deepest_identifier(node)
        class_name = self._text(name_node) if name_node else "UnknownClass"

        members: list[dict[str, Any]] = []
        methods: list[dict[str, Any]] = []

        body = self._find_child(node, "field_declaration_list")
        if body is None:
            for child in node.children:
                if child.type == "declaration_list":
                    body = child
                    break

        prev_class = self._current_class
        self._current_class = class_name

        if body:
            for child in body.children:
                if child.type == "function_definition":
                    method = self._parse_class_method(child, class_name)
                    if method:
                        methods.append(method)
                elif child.type in ("field_declaration", "declaration"):
                    members.extend(self._parse_class_members(child))

        self._current_class = prev_class
        self.classes.append(
            {
                "name": class_name,
                "members": members,
                "methods": methods,
                "line": self._line(node),
            }
        )

    def _parse_class_members(self, node: Node) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        type_parts: list[str] = []
        for child in node.children:
            if child.type in (
                "primitive_type",
                "type_identifier",
                "qualified_identifier",
                "template_type",
            ):
                type_parts.append(self._text(child).strip())
            elif child.type in ("field_declarator", "init_declarator", "identifier"):
                name = self._text(child).strip()
                if name and name not in {"public", "private", "protected"}:
                    members.append(
                        {
                            "name": name.split("=")[0].strip().split("[")[0],
                            "type": " ".join(type_parts).strip() or "unknown",
                            "line": self._line(node),
                        }
                    )
        return members

    def _parse_class_method(self, node: Node, class_name: str) -> dict[str, Any] | None:
        declarator = self._find_child(node, "function_declarator")
        if declarator is None:
            return None
        name_node = self._find_child(declarator, "identifier")
        if name_node is None:
            name_node = self._find_child(declarator, "field_identifier")
        if name_node is None:
            return None

        name = self._text(name_node)
        return_type = self._extract_return_type(node, declarator)
        parameters = self._extract_parameters(declarator)
        body = self._find_child(node, "compound_statement")

        fn_conditions: list[str] = []
        fn_calls: list[str] = []
        fn_loops: list[dict[str, Any]] = []
        fn_variables: list[dict[str, Any]] = []

        prev_function = self._current_function
        self._current_function = name
        self._current_function_variables = fn_variables

        if body is not None:
            condition_count = len(self.conditions)
            call_count = len(self.calls)
            loop_count = len(self.loops)
            self._walk(body)
            fn_conditions = self.conditions[condition_count:]
            fn_calls = [call["function"] for call in self.calls[call_count:]]
            fn_loops = self.loops[loop_count:]

        self._current_function = prev_function
        self._current_function_variables = None

        return {
            "name": name,
            "class": class_name,
            "return_type": return_type,
            "parameters": parameters,
            "recursive": name in fn_calls,
            "conditions": fn_conditions,
            "calls": fn_calls,
            "loops": fn_loops,
            "variables": fn_variables,
            "line": self._line(node),
        }

    def _parse_function(self, node: Node) -> None:
        declarator = self._find_child(node, "function_declarator")
        if declarator is None:
            return

        name_node = self._find_child(declarator, "identifier")
        if name_node is None:
            return

        name = self._text(name_node)
        return_type = self._extract_return_type(node, declarator)
        parameters = self._extract_parameters(declarator)

        body = self._find_child(node, "compound_statement")
        fn_conditions: list[str] = []
        fn_calls: list[str] = []
        fn_loops: list[dict[str, Any]] = []
        fn_variables: list[dict[str, Any]] = []

        prev_function = self._current_function
        self._current_function = name
        self._current_function_variables = fn_variables

        if body is not None:
            condition_count = len(self.conditions)
            call_count = len(self.calls)
            loop_count = len(self.loops)

            self._walk(body)

            fn_conditions = self.conditions[condition_count:]
            fn_calls = [call["function"] for call in self.calls[call_count:]]
            fn_loops = self.loops[loop_count:]

        self._current_function = prev_function
        self._current_function_variables = None

        recursive = name in fn_calls

        self.functions.append(
            {
                "name": name,
                "return_type": return_type,
                "parameters": parameters,
                "recursive": recursive,
                "conditions": fn_conditions,
                "calls": fn_calls,
                "loops": fn_loops,
                "variables": fn_variables,
            }
        )

    def _extract_return_type(self, node: Node, declarator: Node) -> str:
        parts: list[str] = []
        for child in node.children:
            if child == declarator:
                break
            if child.type not in ("comment", "preproc_def", "preproc_include"):
                parts.append(self._text(child).strip())
        return " ".join(parts).strip() or "auto"

    def _extract_parameters(self, declarator: Node) -> list[dict[str, str]]:
        parameters: list[dict[str, str]] = []
        param_list = self._find_child(declarator, "parameter_list")
        if param_list is None:
            return parameters

        for child in param_list.children:
            if child.type != "parameter_declaration":
                continue
            param_type, param_name = self._split_declaration(child)
            parameters.append({"name": param_name, "type": param_type})

        return parameters

    def _split_declaration(self, node: Node) -> tuple[str, str]:
        text = self._text(node).strip()
        identifier = self._find_deepest_identifier(node)
        if identifier:
            name = self._text(identifier)
            type_part = text[: text.rfind(name)].strip()
            return type_part or text, name
        return text, ""

    def _find_deepest_identifier(self, node: Node) -> Node | None:
        identifiers = [
            child
            for child in node.children
            if child.type in ("identifier", "field_identifier", "type_identifier")
        ]
        for child in reversed(node.children):
            nested = self._find_deepest_identifier(child)
            if nested is not None:
                return nested
        if identifiers:
            # Prefer non-type identifiers for variable names.
            for ident in reversed(identifiers):
                if ident.type == "identifier":
                    return ident
            return identifiers[-1]
        return None

    def _extract_local_variables(self, body: Node) -> list[dict[str, Any]]:
        variables: list[dict[str, Any]] = []
        for child in body.children:
            if child.type == "declaration":
                variables.extend(self._parse_variable_declaration(child, scope="local"))
        return variables

    def _parse_global_declaration(self, node: Node) -> None:
        variables = self._parse_variable_declaration(node, scope="global")
        self.global_variables.extend(variables)

    def _parse_local_declaration(self, node: Node) -> None:
        variables = self._parse_variable_declaration(node, scope="local")
        if self._current_function_variables is not None:
            self._current_function_variables.extend(variables)
            return

        if self._current_function is None:
            return
        for fn in self.functions:
            if fn["name"] == self._current_function:
                fn["variables"].extend(variables)
                break

    def _parse_variable_declaration(
        self, node: Node, scope: str
    ) -> list[dict[str, Any]]:
        type_parts: list[str] = []
        variables: list[dict[str, Any]] = []

        for child in node.children:
            if child.type == "init_declarator":
                var_type = " ".join(type_parts).strip()
                var_info = self._parse_init_declarator(child, var_type, scope)
                if var_info:
                    variables.append(var_info)
            elif child.type in (
                "primitive_type",
                "type_identifier",
                "qualified_identifier",
                "struct_specifier",
                "sized_type_specifier",
            ):
                type_parts.append(self._text(child).strip())
            elif child.type == "pointer_declarator":
                type_parts.append(self._text(child).strip())

        return variables

    def _parse_init_declarator(
        self, node: Node, var_type: str, scope: str
    ) -> dict[str, Any] | None:
        array_node = self._find_child(node, "array_declarator")
        name = self._extract_declarator_name(node)
        if name is None:
            return None

        initializer = self._extract_initializer(node)
        full_type = var_type

        if array_node is not None:
            full_type = f"{var_type}[]".strip()
            array_info = {
                "name": name,
                "type": full_type,
                "scope": scope,
                "size": self._extract_array_size(array_node),
                "initializer": initializer,
                "line": self._line(node),
            }
            if not any(item["name"] == name for item in self.arrays):
                self.arrays.append(array_info)

        return {
            "name": name,
            "type": full_type,
            "scope": scope,
            "initializer": initializer,
            "line": self._line(node),
        }

    def _extract_declarator_name(self, node: Node) -> str | None:
        for child in node.children:
            if child.type == "=":
                break
            if child.type == "array_declarator":
                identifier = self._find_child(child, "identifier")
                if identifier is not None:
                    return self._text(identifier)
            elif child.type == "identifier":
                return self._text(child)
            elif child.type == "pointer_declarator":
                identifier = self._find_deepest_identifier(child)
                if identifier is not None:
                    return self._text(identifier)
        return None

    def _extract_array_size(self, array_node: Node) -> str | None:
        for child in array_node.children:
            if child.type not in ("[", "]", "identifier"):
                return self._text(child).strip()
        return None

    def _extract_initializer(self, node: Node) -> Any:
        value_node = self._find_initializer_value_node(node)
        if value_node is None:
            return None

        if value_node.type == "initializer_list":
            values: list[Any] = []
            for child in value_node.children:
                if child.type == "number_literal":
                    values.append(self._parse_number(self._text(child)))
                elif child.type == "string_literal":
                    values.append(self._text(child).strip('"'))
                elif child.type == "identifier":
                    values.append(self._text(child))
            return values

        text = self._text(value_node)
        if value_node.type == "number_literal":
            return self._parse_number(text)
        return text

    def _find_initializer_value_node(self, node: Node) -> Node | None:
        seen_equals = False
        for child in node.children:
            if child.type == "=":
                seen_equals = True
                continue
            if seen_equals and child.type not in (",", ";"):
                return child
        return None

    def _parse_number(self, text: str) -> int | float | str:
        try:
            if "." in text or "e" in text.lower():
                return float(text)
            return int(text, 0)
        except ValueError:
            return text

    def _parse_if(self, node: Node) -> None:
        condition_clause = self._find_child(node, "condition_clause")
        if condition_clause is None:
            return
        for child in condition_clause.children:
            if child.type not in ("(", ")"):
                condition = self._text(child).strip()
                self._add_condition(condition)
                return

    def _add_condition(self, condition: str) -> None:
        normalized = re.sub(r"\s+", " ", condition.strip())
        if normalized and normalized not in self._seen_conditions:
            self._seen_conditions.add(normalized)
            self.conditions.append(normalized)

    def _parse_loop(self, node: Node) -> None:
        loop_type = node.type.replace("_statement", "")
        info: dict[str, Any] = {
            "type": loop_type,
            "function": self._current_function,
            "line": self._line(node),
        }

        if node.type == "for_statement":
            init = None
            condition = None
            update = None
            for child in node.children:
                if child.type in ("declaration", "expression_statement"):
                    init = child
                elif child.type in (
                    "binary_expression",
                    "condition_clause",
                    "identifier",
                    "number_literal",
                    "call_expression",
                ):
                    if condition is None:
                        condition = child
                    elif update is None:
                        update = child
                elif child.type == "update_expression":
                    update = child
            info["init"] = self._text(init).strip() if init else None
            info["condition"] = self._text(condition).strip() if condition else None
            info["update"] = self._text(update).strip() if update else None
        elif node.type == "while_statement":
            condition = self._find_child(node, "condition_clause")
            if condition is None:
                for child in node.children:
                    if child.type in (
                        "binary_expression",
                        "identifier",
                        "call_expression",
                        "condition_clause",
                    ):
                        condition = child
                        break
            info["condition"] = self._text(condition).strip() if condition else None
        elif node.type == "do_statement":
            condition = self._find_child(node, "condition_clause")
            info["condition"] = self._text(condition).strip() if condition else None

        self.loops.append(info)

    def _parse_call(self, node: Node) -> None:
        fn_node = node.children[0] if node.children else None
        if fn_node is None:
            return

        fn_name = self._text(fn_node).strip()
        if "." in fn_name:
            fn_name = fn_name.split(".")[-1]

        arg_list = self._find_child(node, "argument_list")
        arguments: list[str] = []
        if arg_list is not None:
            for child in arg_list.children:
                if child.type not in ("(", ")", ","):
                    arguments.append(self._text(child).strip())

        self.calls.append(
            {
                "function": fn_name,
                "arguments": arguments,
                "caller": self._current_function,
                "line": self._line(node),
            }
        )

    def _parse_field_access(self, node: Node) -> None:
        field = self._find_child(node, "field_identifier")
        base = node.children[0] if node.children else None
        if field is None or base is None:
            return

        self.field_accesses.append(
            {
                "object": self._text(base).strip(),
                "field": self._text(field).strip(),
                "expression": self._text(node).strip(),
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
            if child.type == "subscript_argument_list":
                for arg_child in child.children:
                    if arg_child.type not in ("[", "]"):
                        index_expr = self._text(arg_child).strip()
                        break
            elif child.type not in ("[", "]"):
                index_expr = self._text(child).strip()
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

    def _collect_all_variables(self) -> list[dict[str, Any]]:
        variables = list(self.global_variables)
        for fn in self.functions:
            variables.extend(fn.get("variables", []))
        return variables

    def _detect_data_structures(self) -> list[str]:
        structures: list[str] = []
        code_lower = self.code.lower()

        tree_fields = {
            access["field"].lower()
            for access in self.field_accesses
            if access["field"].lower() in TREE_POINTER_FIELDS
        }
        has_left_right = {"left", "right"}.issubset(tree_fields) or bool(
            {"left", "right"} & tree_fields
        )
        has_node_type = any(
            "node" in param.get("type", "").lower()
            for fn in self.functions
            for param in fn.get("parameters", [])
        )
        if has_left_right or has_node_type:
            structures.append("binary_tree")

        if any(field.lower() in LINKED_LIST_FIELDS for field in tree_fields):
            structures.append("linked_list")

        if self.arrays or self.subscript_accesses:
            structures.append("array")

        if any(hint in code_lower for hint in GRAPH_HINTS):
            structures.append("graph")
        elif re.search(r"vector\s*<\s*vector\s*<", self.code):
            structures.append("graph")

        if re.search(r"\b(stack|push|pop|top)\b", code_lower):
            structures.append("stack")

        if re.search(r"\b(queue|enqueue|dequeue|front|rear)\b", code_lower):
            structures.append("queue")

        # Preserve order while deduplicating.
        seen: set[str] = set()
        ordered: list[str] = []
        for item in structures:
            if item not in seen:
                seen.add(item)
                ordered.append(item)

        return ordered

    def _detect_algorithm(self, data_structures: list[str]) -> str | None:
        if self._looks_like_tree_traversal():
            order = self._tree_traversal_order()
            if order:
                return f"{order}_traversal"

        if self._looks_like_binary_search():
            return "binary_search"

        if self._looks_like_merge_sort():
            return "merge_sort"

        if self._looks_like_quick_sort():
            return "quick_sort"

        if self._looks_like_bubble_sort():
            return "bubble_sort"

        if self._looks_like_selection_sort():
            return "selection_sort"

        if self._looks_like_insertion_sort():
            return "insertion_sort"

        if "graph" in data_structures and self._looks_like_bfs():
            return "bfs"

        if "graph" in data_structures and self._looks_like_dfs():
            return "dfs"

        if any(fn.get("recursive") for fn in self.functions):
            return "recursion"

        if "array" in data_structures and self.arrays:
            return "array_processing"

        return None

    def _looks_like_tree_traversal(self) -> bool:
        return "binary_tree" in self._detect_data_structures() and any(
            fn.get("recursive") for fn in self.functions
        )

    def _tree_traversal_order(self) -> str | None:
        for fn in self.functions:
            if not fn.get("recursive"):
                continue

            body_calls = [
                call
                for call in self.calls
                if call.get("caller") == fn["name"] and call["function"] == fn["name"]
            ]
            if len(body_calls) < 2:
                continue

            left_indices = [
                idx
                for idx, call in enumerate(body_calls)
                if any("left" in arg for arg in call["arguments"])
            ]
            right_indices = [
                idx
                for idx, call in enumerate(body_calls)
                if any("right" in arg for arg in call["arguments"])
            ]
            if not left_indices or not right_indices:
                continue

            first_left = min(left_indices)
            first_right = min(right_indices)

            visit_between = any(
                "data" in access["field"].lower()
                or "val" in access["field"].lower()
                or "value" in access["field"].lower()
                for access in self.field_accesses
                if access.get("function") == fn["name"]
            )

            if first_left < first_right:
                return "inorder" if visit_between else "preorder"
            return "postorder"

        return None

    def _looks_like_binary_search(self) -> bool:
        names = {var["name"].lower() for var in self._collect_all_variables()}
        condition_text = " ".join(self.conditions).lower()
        code_lower = self.code.lower()

        has_pointers = {"low", "high"}.issubset(names) or (
            {"low", "high"}.issubset(set(re.findall(r"\b(low|high|mid)\b", code_lower)))
        )
        has_mid = (
            "mid" in names
            or "mid" in condition_text
            or bool(re.search(r"\bmid\b", code_lower))
        )
        has_array_mid = "arr[mid]" in condition_text or any(
            access["index"] == "mid" for access in self.subscript_accesses
        )

        return (
            has_pointers and has_mid and (has_array_mid or "while" in str(self.loops))
        )

    def _looks_like_bubble_sort(self) -> bool:
        nested = len(self.loops) >= 2
        has_swap = (
            any(call["function"] in {"swap", "std::swap"} for call in self.calls)
            or "swap" in self.code.lower()
        )
        return nested and has_swap and "array" in self._detect_data_structures()

    def _looks_like_selection_sort(self) -> bool:
        code_lower = self.code.lower()
        return "array" in self._detect_data_structures() and (
            "min_index" in code_lower or "minindex" in code_lower
        )

    def _looks_like_insertion_sort(self) -> bool:
        code_lower = self.code.lower()
        return "array" in self._detect_data_structures() and "key" in code_lower

    def _looks_like_merge_sort(self) -> bool:
        code_lower = self.code.lower()
        if re.search(r"\bmerge_?sort\b", code_lower):
            return True
        fn_names = {fn["name"].lower() for fn in self.functions}
        has_merge_fn = "merge" in fn_names or "mergesort" in fn_names
        recursive = any(fn.get("recursive") for fn in self.functions)
        return has_merge_fn and recursive

    def _looks_like_quick_sort(self) -> bool:
        code_lower = self.code.lower()
        if re.search(r"\bquick_?sort\b", code_lower):
            return True
        fn_names = {fn["name"].lower() for fn in self.functions}
        has_partition = "partition" in fn_names or "partition" in code_lower
        recursive = any(fn.get("recursive") for fn in self.functions)
        return has_partition and recursive

    def _looks_like_bfs(self) -> bool:
        code_lower = self.code.lower()
        return "queue" in code_lower and bool(self.loops or self.calls)

    def _looks_like_dfs(self) -> bool:
        code_lower = self.code.lower()
        return (
            "visited" in code_lower or any(fn.get("recursive") for fn in self.functions)
        ) and "graph" in self._detect_data_structures()

    def _derive_operations(
        self, data_structures: list[str], algorithm: str | None
    ) -> list[str]:
        operations: list[str] = []

        for array in self.arrays:
            init = array.get("initializer")
            if init:
                operations.append(f"initialize array {array['name']} = {init}")
            else:
                operations.append(f"declare array {array['name']}")

        for call in self.calls:
            arg_text = ", ".join(call["arguments"])
            prefix = f"{call['caller']} calls " if call.get("caller") else "calls "
            operations.append(f"{prefix}{call['function']}({arg_text})")

        for condition in self.conditions:
            operations.append(f"check condition: {condition}")

        for loop in self.loops:
            condition = loop.get("condition") or "unknown"
            operations.append(f"{loop['type']} loop while {condition}")

        for access in self.field_accesses:
            operations.append(f"access {access['expression']}")

        for access in self.subscript_accesses:
            operations.append(f"access {access['expression']}")

        if algorithm:
            operations.append(f"detected algorithm: {algorithm}")

        if data_structures:
            operations.append("detected data structures: " + ", ".join(data_structures))

        return operations


def parse_cpp(code: str) -> dict[str, Any]:
    return CppParser(code).parse()
