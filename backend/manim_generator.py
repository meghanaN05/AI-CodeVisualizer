"""Convert structured animation plans into executable Manim code."""

from __future__ import annotations

import json
from typing import Any


def generate_manim_code(animation_plan: dict[str, Any]) -> str:
    scenes_json = json.dumps(animation_plan.get("scenes", []))
    title = animation_plan.get("title", "Code Visualization")

    return f"""from manim import *
import json
import math


class CodeVisualization(Scene):
    SCENES = json.loads({scenes_json!r})

    def construct(self):
        self.camera.background_color = "#1a1a2e"
        self.array_boxes = []
        self.array_labels = []
        self.array_values = []
        self.tree_nodes = {{}}
        self.tree_edges = VGroup()
        self.graph_nodes = {{}}
        self.graph_edges = {{}}
        self.graph_group = None
        self.pointer = None
        self.caption = None
        self.stack_items = VGroup()
        self.var_panel = None
        self.hashmap_group = None
        self.heap_group = None

        for step in self.SCENES:
            action = step.get("action")
            if action == "show_title":
                self._show_title(step.get("text", {title!r}))
            elif action == "create_array":
                self._create_array(step.get("values", []))
            elif action == "highlight_index":
                self._highlight_index(step.get("index", 0), step.get("label", ""), step.get("caption"))
            elif action == "highlight_range":
                self._highlight_index(step.get("index", 0), step.get("label", ""), step.get("caption"))
            elif action == "compare_indices":
                self._compare_indices(step.get("index", 0), step.get("label", "1"), step.get("caption"))
            elif action == "swap_indices":
                self._swap_indices(step.get("index", 0), step.get("label", "1"), step.get("values", []), step.get("caption"))
            elif action == "show_tree":
                self._show_tree(step.get("tree", {{}}))
            elif action == "highlight_node":
                self._highlight_node(step.get("node"), step.get("caption"))
            elif action == "move_pointer":
                self._move_pointer(step.get("from"), step.get("to"), step.get("caption"))
            elif action == "visit_node":
                self._visit_node(step.get("node"), step.get("caption"))
            elif action == "show_graph":
                self._show_graph(
                    step.get("nodes", []),
                    step.get("edges", []),
                    step.get("layout"),
                    step.get("directed", False),
                    step.get("caption"),
                )
            elif action == "show_variables":
                self._show_variables(step.get("variables", {{}}), step.get("caption"))
            elif action == "push_stack":
                self._push_stack(step.get("label", ""), step.get("caption"))
            elif action == "pop_stack":
                self._pop_stack(step.get("label", ""), step.get("caption"))
            elif action == "show_caption":
                self._show_caption(step.get("text", ""))
            elif action == "show_class_methods":
                self._show_class_methods(step.get("text", ""), step.get("nodes", []), step.get("caption"))
            elif action == "show_hashmap":
                self._show_hashmap(step.get("text", "map"), step.get("values", []), step.get("caption"))
            elif action == "hashmap_insert":
                self._hashmap_insert(step.get("text", "map"), step.get("label", ""), step.get("caption"))
            elif action == "show_heap":
                self._show_heap(step.get("values", []), step.get("caption"))
            elif action == "heap_push":
                self._heap_push(step.get("label", ""), step.get("caption"))
            elif action == "heap_pop":
                self._heap_pop(step.get("label", ""), step.get("caption"))
            elif action == "show_method_flow":
                self._show_method_flow(step.get("text", ""), step.get("caption"))
            elif action == "show_weighted_graph":
                self._show_weighted_graph(step.get("graph", {{}}), step.get("caption"))
            elif action == "relax_edge":
                self._relax_edge(step.get("from"), step.get("to"), step.get("weight"), step.get("caption"))
            elif action == "update_distance":
                self._update_distance(step.get("node"), step.get("distances", {{}}), step.get("label"), step.get("caption"))
            elif action == "show_shortest_path":
                self._show_shortest_path(step.get("path", []), step.get("graph", {{}}), step.get("caption"))

        self.wait(1)

    def _show_title(self, text):
        title = Text(text, font_size=48, color=YELLOW)
        subtitle = Text("AI Code Visualizer", font_size=24, color=GRAY_B).next_to(title, DOWN)
        group = VGroup(title, subtitle)
        self.play(Write(title), FadeIn(subtitle))
        self.wait(1.2)
        self.play(FadeOut(group))

    def _show_caption(self, text):
        if not text:
            return
        new_caption = Text(str(text), font_size=28, color=WHITE).to_edge(DOWN, buff=0.5)
        if self.caption:
            self.play(Transform(self.caption, new_caption))
        else:
            self.caption = new_caption
            self.play(FadeIn(self.caption))
        self.wait(0.8)

    def _create_array(self, values):
        if hasattr(self, "array_group") and self.array_group in self.mobjects:
            self.play(FadeOut(self.array_group))
            self.remove(self.array_group)
        self.array_boxes = []
        self.array_labels = []
        self.array_values = [str(v) for v in values]
        group = VGroup()
        spacing = 1.6
        start_x = -((len(values) - 1) * spacing) / 2

        for i, value in enumerate(self.array_values):
            box = RoundedRectangle(width=1.3, height=1.3, corner_radius=0.1, color=BLUE, fill_opacity=0.15)
            label = Text(value, font_size=36, color=WHITE)
            label.move_to(box.get_center())
            item = VGroup(box, label)
            item.move_to(RIGHT * (start_x + i * spacing))
            self.array_boxes.append(box)
            self.array_labels.append(label)
            group.add(item)

        self.array_group = group
        self.play(LaggedStart(*[Create(box) for box in self.array_boxes], lag_ratio=0.15))
        self.play(LaggedStart(*[Write(label) for label in self.array_labels], lag_ratio=0.1))
        self.wait(0.5)

    def _highlight_index(self, index, label, caption):
        if not self.array_boxes:
            return
        index = max(0, min(int(index), len(self.array_boxes) - 1))
        if caption:
            self._show_caption(caption)

        animations = []
        for i, box in enumerate(self.array_boxes):
            color = YELLOW if i == index else BLUE
            opacity = 0.45 if i == index else 0.15
            animations.append(box.animate.set_color(color).set_fill(color, opacity=opacity))

        if self.pointer:
            self.remove(self.pointer)
        target = self.array_boxes[index].get_bottom() + DOWN * 0.2
        self.pointer = Arrow(start=target + DOWN * 0.8, end=target, color=YELLOW, buff=0.05)
        pointer_label = Text(str(label or f"i = {{index}}"), font_size=24, color=YELLOW)
        pointer_label.next_to(self.pointer, DOWN, buff=0.1)
        self.pointer = VGroup(self.pointer, pointer_label)

        self.play(*animations, GrowArrow(self.pointer[0]), FadeIn(self.pointer[1]))
        self.wait(0.7)

    def _compare_indices(self, index, other, caption):
        if not self.array_boxes:
            return
        i = max(0, min(int(index), len(self.array_boxes) - 1))
        j = max(0, min(int(other), len(self.array_boxes) - 1))
        if caption:
            self._show_caption(caption)
        anims = []
        for idx, box in enumerate(self.array_boxes):
            if idx in (i, j):
                anims.append(box.animate.set_color(ORANGE).set_fill(ORANGE, opacity=0.45))
            else:
                anims.append(box.animate.set_color(BLUE).set_fill(BLUE, opacity=0.15))
        self.play(*anims)
        self.wait(0.6)

    def _swap_indices(self, index, other, values, caption):
        if values:
            self._create_array(values)
        if caption:
            self._show_caption(caption)
        self.wait(0.5)

    def _show_tree(self, tree):
        self.tree_nodes = {{}}
        self.tree_edges = VGroup()
        if self.tree_edges in self.mobjects:
            self.remove(self.tree_edges)

        positions = {{}}
        self._assign_tree_positions(tree, 0, 0, 2.8, positions)
        nodes_group = VGroup()
        edges_group = VGroup()

        for value, (x, y) in positions.items():
            circle = Circle(radius=0.45, color=BLUE, fill_opacity=0.2)
            label = Text(str(value), font_size=30, color=WHITE)
            label.move_to(circle.get_center())
            node = VGroup(circle, label)
            node.move_to(RIGHT * x + UP * y)
            self.tree_nodes[str(value)] = node
            nodes_group.add(node)

        def add_edges(node, x, y, spread):
            if not node:
                return
            value = str(node.get("value"))
            for side, child_key in (("left", "left"), ("right", "right")):
                child = node.get(child_key)
                if child and "value" in child:
                    cx, cy = positions[str(child["value"])]
                    start = self.tree_nodes[value][0].get_center()
                    end = self.tree_nodes[str(child["value"])][0].get_center()
                    edge = Line(start, end, color=GRAY_B, stroke_width=3)
                    edges_group.add(edge)
                    add_edges(child, cx, cy, spread / 2)

        add_edges(tree, 0, 0, 2.8)
        self.tree_edges = edges_group
        self.play(Create(edges_group), LaggedStart(*[GrowFromCenter(n[0]) for n in nodes_group], lag_ratio=0.1))
        self.play(LaggedStart(*[Write(n[1]) for n in nodes_group], lag_ratio=0.1))
        self.wait(0.6)

    def _assign_tree_positions(self, node, x, y, spread, positions):
        if not node or "value" not in node:
            return
        positions[str(node["value"])] = (x, y)
        if node.get("left"):
            self._assign_tree_positions(node["left"], x - spread, y - 1.8, spread / 2, positions)
        if node.get("right"):
            self._assign_tree_positions(node["right"], x + spread, y - 1.8, spread / 2, positions)

    def _highlight_node(self, node, caption):
        if caption:
            self._show_caption(caption)
        key = str(node)
        if key not in self.tree_nodes:
            return
        anims = []
        for value, group in self.tree_nodes.items():
            circle = group[0]
            if value == key:
                anims.append(circle.animate.set_color(YELLOW).set_fill(YELLOW, opacity=0.5))
            else:
                anims.append(circle.animate.set_color(BLUE).set_fill(BLUE, opacity=0.2))
        self.play(*anims)
        self.wait(0.6)

    def _move_pointer(self, from_node, to_node, caption):
        if caption:
            self._show_caption(caption)
        start_key = str(from_node)
        end_key = str(to_node)
        if start_key in self.tree_nodes and end_key in self.tree_nodes:
            arrow = Arrow(
                self.tree_nodes[start_key][0].get_center(),
                self.tree_nodes[end_key][0].get_center(),
                color=YELLOW,
                buff=0.45,
                stroke_width=4,
            )
            self.play(GrowArrow(arrow))
            self.play(FadeOut(arrow))
        self.wait(0.4)

    def _visit_node(self, node, caption):
        key = str(node)
        if key in self.tree_nodes:
            check = Text("✓", font_size=28, color=GREEN).next_to(self.tree_nodes[key], UP, buff=0.15)
            if caption:
                self._show_caption(caption)
            self.play(FadeIn(check, scale=0.5))
            self.wait(0.4)
            self.play(FadeOut(check))

    def _show_graph(self, nodes, edges=None, layout=None, directed=False, caption=None):
        scene = {{
            "nodes": nodes,
            "edges": edges,
            "layout": layout,
            "directed": directed,
        }}
        self._render_graph(scene, caption)

    def _normalize_graph_scene(self, scene):
        scene = scene or {{}}
        raw_nodes = scene.get("nodes") or []
        raw_edges = scene.get("edges") or []
        directed = bool(scene.get("directed", False))
        node_labels = []
        known = set()

        for node in raw_nodes:
            if isinstance(node, dict):
                node_id = node.get("id")
                node_label = node.get("label", node_id)
            else:
                node_id = node
                node_label = node
            if node_id is None:
                continue
            key = str(node_id)
            if key in known:
                continue
            known.add(key)
            node_labels.append({{"id": key, "label": str(node_label)}})

        normalized_edges = []
        for edge in raw_edges:
            source = None
            target = None
            weight = None
            if isinstance(edge, dict):
                source = edge.get("from")
                target = edge.get("to")
                weight = edge.get("weight")
            elif isinstance(edge, (list, tuple)) and len(edge) >= 2:
                source = edge[0]
                target = edge[1]
                weight = edge[2] if len(edge) >= 3 else None
            if source is None or target is None:
                continue
            source = str(source)
            target = str(target)
            normalized_edges.append({{"from": source, "to": target, "weight": weight}})
            if source not in known:
                known.add(source)
                node_labels.append({{"id": source, "label": source}})
            if target not in known:
                known.add(target)
                node_labels.append({{"id": target, "label": target}})

        return {{
            "nodes": node_labels,
            "edges": normalized_edges,
            "layout": scene.get("layout") or {{}},
            "directed": directed,
        }}

    def _graph_positions(self, nodes, layout):
        positions = {{}}
        if layout:
            positions.update({{
                str(name): RIGHT * float(pt[0]) + UP * float(pt[1])
                for name, pt in layout.items()
                if isinstance(pt, (list, tuple)) and len(pt) >= 2
            }})

        missing = [node for node in nodes if node["id"] not in positions]
        if not missing:
            return positions

        if len(missing) == 1:
            positions[missing[0]["id"]] = ORIGIN
            return positions

        count = len(missing)
        radius = 1.8 if count <= 3 else 2.4 if count <= 6 else 3.0
        for index, node in enumerate(missing):
            angle = TAU * index / max(count, 1)
            point = RIGHT * (radius * math.cos(angle)) + UP * (radius * math.sin(angle))
            positions[node["id"]] = point
        return positions

    def _create_graph_nodes(self, nodes, positions):
        node_group = VGroup()
        self.graph_nodes = {{}}
        self.tree_nodes = {{}}

        for node in nodes:
            node_id = node["id"]
            label_text = node["label"]
            pos = positions.get(node_id, ORIGIN)
            circle = Circle(radius=0.45, color=TEAL, fill_opacity=0.25)
            label = Text(str(label_text), font_size=30, color=WHITE).move_to(circle.get_center())
            group = VGroup(circle, label).move_to(pos)
            self.graph_nodes[node_id] = group
            self.tree_nodes[node_id] = group
            node_group.add(group)
        return node_group

    def _edge_label_position(self, start, end):
        mid = (start + end) / 2
        delta = end - start
        length = math.sqrt(float(delta[0] ** 2 + delta[1] ** 2))
        if length == 0:
            return mid + UP * 0.25
        perp = LEFT * (float(delta[1]) / length) + UP * (float(delta[0]) / length)
        return mid + perp * 0.25

    def _create_graph_edges(self, edges, directed):
        edge_group = VGroup()
        weight_group = VGroup()
        self.graph_edges = {{}}

        for edge in edges:
            source = edge["from"]
            target = edge["to"]
            weight = edge.get("weight")
            if source not in self.graph_nodes or target not in self.graph_nodes:
                continue
            start = self.graph_nodes[source][0].get_center()
            end = self.graph_nodes[target][0].get_center()
            line = (
                Arrow(start, end, color=GRAY_B, buff=0.5, stroke_width=3, max_tip_length_to_length_ratio=0.12)
                if directed
                else Line(start, end, color=GRAY_B, stroke_width=3)
            )
            edge_group.add(line)
            label_obj = None
            label_pos = None
            if weight is not None:
                label_pos = self._edge_label_position(start, end)
                label_obj = Text(str(weight), font_size=22, color=ORANGE).move_to(label_pos)
                weight_group.add(label_obj)
            info = {{"line": line, "label": label_obj, "mid": label_pos, "weight": weight}}
            self.graph_edges[(source, target)] = info
            if not directed:
                self.graph_edges[(target, source)] = info
        return edge_group, weight_group

    def _render_graph(self, scene, caption=None):
        if caption:
            self._show_caption(caption)
        if self.graph_group in self.mobjects:
            self.play(FadeOut(self.graph_group))

        normalized = self._normalize_graph_scene(scene)
        nodes = normalized["nodes"]
        edges = normalized["edges"]
        if not nodes:
            self._show_caption("No graph nodes were provided")
            return

        positions = self._graph_positions(nodes, normalized.get("layout") or {{}})
        node_group = self._create_graph_nodes(nodes, positions)
        edge_group, weight_group = self._create_graph_edges(edges, normalized.get("directed", False))

        groups = [edge_group, node_group]
        if len(weight_group) > 0:
            groups.insert(1, weight_group)
        self.graph_group = VGroup(*groups)
        self.play(
            Create(edge_group),
            LaggedStart(*[GrowFromCenter(n[0]) for n in node_group], lag_ratio=0.12),
        )
        self.play(LaggedStart(*[Write(n[1]) for n in node_group], lag_ratio=0.1))
        if len(weight_group) > 0:
            self.play(FadeIn(weight_group))
        self.wait(0.6)

    def _show_variables(self, variables, caption):
        if caption:
            self._show_caption(caption)
        lines = [f"{{name}} = {{value}}" for name, value in variables.items()]
        text = "\\n".join(lines)
        panel = VGroup()
        bg = RoundedRectangle(width=4.5, height=0.8 + 0.45 * len(lines), corner_radius=0.15, color=BLUE_D, fill_opacity=0.35)
        label = Text(text, font_size=28, color=WHITE, line_spacing=1.1)
        label.move_to(bg.get_center())
        panel.add(bg, label)
        panel.to_edge(RIGHT, buff=0.5)
        if self.var_panel:
            self.play(FadeOut(self.var_panel))
        self.var_panel = panel
        self.play(FadeIn(panel))

    def _push_stack(self, label, caption):
        if caption:
            self._show_caption(caption)
        frame = RoundedRectangle(width=5, height=0.7, corner_radius=0.1, color=PURPLE, fill_opacity=0.25)
        text = Text(str(label), font_size=26, color=WHITE).move_to(frame.get_center())
        item = VGroup(frame, text)
        item.to_edge(LEFT, buff=1).shift(DOWN * len(self.stack_items) * 0.8)
        self.stack_items.add(item)
        self.play(FadeIn(item, shift=UP * 0.3))
        self.wait(0.4)

    def _pop_stack(self, label, caption):
        if caption:
            self._show_caption(caption)
        if len(self.stack_items) > 0:
            item = self.stack_items[-1]
            self.play(FadeOut(item, shift=DOWN * 0.3))
            self.stack_items.remove(item)
        self.wait(0.4)

    def _show_class_methods(self, class_name, methods, caption):
        if caption:
            self._show_caption(caption)
        title = Text(str(class_name), font_size=40, color=YELLOW)
        title.to_edge(UP, buff=0.6)
        items = VGroup()
        for i, method in enumerate(methods[:8]):
            box = RoundedRectangle(width=5.5, height=0.65, corner_radius=0.08, color=BLUE_D, fill_opacity=0.3)
            label = Text(f"  {{method}}()", font_size=24, color=WHITE, font="Consolas")
            label.move_to(box.get_center())
            row = VGroup(box, label)
            row.shift(DOWN * i * 0.85)
            items.add(row)
        items.next_to(title, DOWN, buff=0.4)
        group = VGroup(title, items)
        self.play(Write(title), LaggedStart(*[FadeIn(row, shift=RIGHT * 0.2) for row in items], lag_ratio=0.12))
        self.wait(1.2)
        self.play(FadeOut(group))

    def _show_hashmap(self, name, entries, caption):
        if caption:
            self._show_caption(caption)
        if self.hashmap_group and self.hashmap_group in self.mobjects:
            self.play(FadeOut(self.hashmap_group))
        header = Text(f"hash_map: {{name}}", font_size=32, color=TEAL).to_edge(UP, buff=1.0)
        rows = VGroup()
        data = entries or [["key", "value"]]
        for i, entry in enumerate(data[:5]):
            key = str(entry[0]) if isinstance(entry, (list, tuple)) and entry else str(entry)
            val = str(entry[1]) if isinstance(entry, (list, tuple)) and len(entry) > 1 else "..."
            box = RoundedRectangle(width=7, height=0.7, corner_radius=0.08, color=TEAL, fill_opacity=0.2)
            text = Text(f"  {{key}}  →  {{val}}", font_size=22, color=WHITE, font="Consolas")
            text.move_to(box.get_center())
            row = VGroup(box, text).shift(DOWN * i * 0.85)
            rows.add(row)
        rows.next_to(header, DOWN, buff=0.3)
        self.hashmap_group = VGroup(header, rows)
        self.play(FadeIn(header), LaggedStart(*[FadeIn(r, shift=RIGHT * 0.15) for r in rows], lag_ratio=0.1))
        self.wait(0.8)

    def _hashmap_insert(self, name, label, caption):
        if caption:
            self._show_caption(caption)
        box = RoundedRectangle(width=7, height=0.7, corner_radius=0.08, color=GREEN, fill_opacity=0.35)
        text = Text(f"  + {{label}}", font_size=22, color=WHITE, font="Consolas")
        text.move_to(box.get_center())
        row = VGroup(box, text)
        if self.hashmap_group:
            row.next_to(self.hashmap_group, DOWN, buff=0.2)
        self.play(FadeIn(row, shift=UP * 0.2))
        self.wait(0.6)
        self.play(FadeOut(row))

    def _show_heap(self, values, caption):
        if caption:
            self._show_caption(caption)
        if self.heap_group and self.heap_group in self.mobjects:
            self.play(FadeOut(self.heap_group))
        title = Text("priority_queue (max-heap)", font_size=28, color=ORANGE).to_edge(UP, buff=1.0)
        nodes = VGroup()
        positions = [UP * 1.2, LEFT * 2 + DOWN * 0.5, RIGHT * 2 + DOWN * 0.5, LEFT * 3.5 + DOWN * 2, RIGHT * 3.5 + DOWN * 2]
        items = values or [("item", 10), ("item", 7)]
        for i, item in enumerate(items[:5]):
            val = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else item
            circle = Circle(radius=0.5, color=ORANGE, fill_opacity=0.3)
            label = Text(str(val), font_size=26, color=WHITE)
            label.move_to(circle.get_center())
            node = VGroup(circle, label).move_to(positions[i] if i < len(positions) else DOWN * i)
            nodes.add(node)
        edges = VGroup()
        if len(nodes) > 1:
            edges.add(Line(nodes[0].get_center(), nodes[1].get_center(), color=GRAY_B))
        if len(nodes) > 2:
            edges.add(Line(nodes[0].get_center(), nodes[2].get_center(), color=GRAY_B))
        self.heap_group = VGroup(title, edges, nodes)
        self.play(Write(title), Create(edges), LaggedStart(*[GrowFromCenter(n[0]) for n in nodes], lag_ratio=0.15))
        self.wait(0.8)

    def _heap_push(self, label, caption):
        if caption:
            self._show_caption(caption)
        circle = Circle(radius=0.5, color=GREEN, fill_opacity=0.4)
        text = Text(str(label), font_size=22, color=WHITE)
        text.move_to(circle.get_center())
        node = VGroup(circle, text).move_to(UP * 2)
        self.play(FadeIn(node, shift=DOWN * 0.4))
        self.wait(0.5)
        self.play(FadeOut(node))

    def _heap_pop(self, label, caption):
        if caption:
            self._show_caption(caption)
        if self.heap_group and len(self.heap_group) > 2 and len(self.heap_group[2]) > 0:
            top = self.heap_group[2][0]
            self.play(top.animate.set_color(RED).scale(1.2))
            self.wait(0.3)
            popped = Text(f"pop → {{label}}", font_size=28, color=RED).to_edge(RIGHT, buff=0.8)
            self.play(FadeOut(top, shift=UP * 0.5), Write(popped))
            self.wait(0.5)
            self.play(FadeOut(popped))
        else:
            self._show_caption(f"pop → {{label}}")

    def _show_method_flow(self, method_name, caption):
        if caption:
            self._show_caption(caption)
        banner = RoundedRectangle(width=8, height=0.9, corner_radius=0.1, color=PURPLE, fill_opacity=0.35)
        label = Text(f"▶ {{method_name}}()", font_size=30, color=WHITE, font="Consolas")
        label.move_to(banner.get_center())
        group = VGroup(banner, label)
        self.play(FadeIn(group, scale=0.9))
        self.wait(0.7)
        self.play(FadeOut(group))

    def _show_weighted_graph(self, graph, caption):
        self._render_graph(graph or {{}}, caption)

    def _relax_edge(self, source, target, weight, caption):
        if caption:
            self._show_caption(caption)
        key = (str(source), str(target))
        info = getattr(self, "graph_edges", {{}}).get(key)
        if info:
            line = info["line"]
            self.play(line.animate.set_color(YELLOW).set_stroke(width=5))
            self.wait(0.5)
            self.play(line.animate.set_color(GRAY_B).set_stroke(width=3))
        else:
            self._show_caption(f"relax {{source}}→{{target}} (weight {{weight}})")

    def _update_distance(self, node, distances, label, caption):
        if caption:
            self._show_caption(caption)
        nid = str(node)
        node_group = getattr(self, "graph_nodes", {{}}).get(nid)
        if node_group is not None:
            self.play(node_group[0].animate.set_color(GREEN).set_fill(GREEN, opacity=0.5))
        dist_text = Text(f"dist[{{nid}}] = {{label}}", font_size=24, color=GREEN)
        if node_group is not None:
            dist_text.next_to(node_group, UP, buff=0.15)
        else:
            dist_text.to_edge(UP, buff=1.0)
        self.play(FadeIn(dist_text))
        self.wait(0.5)
        self.play(FadeOut(dist_text))
        if node_group is not None:
            self.play(node_group[0].animate.set_color(TEAL).set_fill(TEAL, opacity=0.25))

    def _show_shortest_path(self, path, graph, caption):
        if caption:
            self._show_caption(caption)
        edges = getattr(self, "graph_edges", {{}})
        unique_lines = {{}}
        for i in range(len(path) - 1):
            info = edges.get((str(path[i]), str(path[i + 1])))
            if info:
                unique_lines[id(info["line"])] = info["line"]
        self.play(*[line.animate.set_color(GREEN).set_stroke(width=6) for line in unique_lines.values()])
        for i, node in enumerate(path):
            node_group = self.graph_nodes.get(str(node))
            if node_group is not None:
                self.play(node_group[0].animate.set_color(GREEN).set_fill(GREEN, opacity=0.6))
        self.wait(1.0)
"""
