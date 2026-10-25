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

    def play(self, *args, **kwargs):
        kwargs["run_time"] = kwargs.get("run_time", 1.0) * self.speed
        super().play(*args, **kwargs)

    def wait(self, duration=1.0, *args, **kwargs):
        super().wait(duration * self.speed, *args, **kwargs)

    def construct(self):
        # Plans with many steps play faster rather than being truncated.
        self.speed = max(0.3, min(1.0, 60 / max(len(self.SCENES), 1)))
        self.camera.background_color = "#1a1a2e"
        self.array_boxes = []
        self.array_labels = []
        self.array_values = []
        self.tree_nodes = {{}}
        self.tree_edges = VGroup()
        self._tree_objects = []
        self.graph_nodes = {{}}
        self.graph_edges = {{}}
        self._graph_objects = []
        self.graph_group = None
        self.pointer = None
        self.caption = None
        self.stack_items = VGroup()
        self.var_panel = None
        self.hashmap_group = None
        self.heap_group = None
        self.arch_components = {{}}
        self.arch_connections = {{}}
        self._arch_objects = []
        self.grid_cells = {{}}
        self.grid_group = None
        self.grid_highlight = None
        self.ll_group = None
        self.hashmap_entries = {{}}
        self.array_anchor = None
        self.named_pointers = None
        self.collection_group = None
        self.pointer_order = []
        self.current_graph_node = None

        for step in self.SCENES:
            action = step.get("action")
            if action == "show_title":
                self._show_title(step.get("text", {title!r}))
            elif action == "create_array":
                self._create_array(step.get("values", []), (step.get("layout") or {{}}).get("anchor"), step.get("caption"))
            elif action == "highlight_index":
                self._highlight_index(step.get("index", 0), step.get("label", ""), step.get("caption"))
            elif action == "highlight_range":
                self._highlight_index(step.get("index", 0), step.get("label", ""), step.get("caption"))
            elif action == "compare_indices":
                self._compare_indices(step.get("index", 0), step.get("label", "1"), step.get("caption"))
            elif action == "swap_indices":
                self._swap_indices(step.get("index", 0), step.get("label", "1"), step.get("values", []), step.get("caption"))
            elif action == "show_tree":
                self._show_tree(step.get("tree", {{}}), step.get("layout"))
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
                self._hashmap_insert(step.get("text", "map"), step.get("label", ""), step.get("caption"), step.get("values"))
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
            elif action == "chapter":
                self._show_chapter(step.get("text", ""))
            elif action == "show_architecture":
                self._show_architecture(
                    step.get("components", []),
                    step.get("connections", []),
                    step.get("layout", {{}}),
                    step.get("caption"),
                )
            elif action == "show_flow":
                self._show_flow(step.get("from"), step.get("to"), step.get("caption"))
            elif action == "show_pointers":
                self._show_pointers(step.get("variables", {{}}))
            elif action == "show_collection":
                self._show_collection(step.get("text", ""), step.get("values", []), step.get("label", "list"), step.get("caption"))
            elif action == "compare_value":
                self._compare_value(step.get("index", 0), step.get("caption"))
            elif action == "highlight_indices":
                self._highlight_indices(step.get("values", []), step.get("caption"))
            elif action == "set_index":
                self._set_index(step.get("index", 0), step.get("values", []), step.get("caption"))
            elif action == "show_grid":
                self._show_grid(step.get("values", []), step.get("caption"))
            elif action == "set_cell":
                self._set_cell(step.get("row", 0), step.get("col", 0), step.get("values", []), step.get("caption"))
            elif action == "highlight_cell":
                self._highlight_cell(step.get("row", 0), step.get("col", 0), step.get("caption"))
            elif action == "show_linked_list":
                self._show_linked_list(step.get("nodes", []), step.get("edges", []), step.get("variables", {{}}), step.get("caption"))
            elif action == "highlight_component":
                self._highlight_component(step.get("component"), step.get("caption"))

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

    def _create_array(self, values, anchor=None, caption=None):
        if caption:
            self._show_caption(caption)
        if getattr(self, "array_boxes", None) and any(b in self.mobjects for b in self.array_boxes):
            self.play(FadeOut(*self.array_boxes), FadeOut(*self.array_labels))
            self.remove(*self.array_boxes, *self.array_labels)
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

        if group.width > 12.5:
            group.scale_to_fit_width(12.5)
        if anchor is None:
            anchor = self.array_anchor
        self.array_anchor = anchor
        if anchor == "bottom":
            group.shift(DOWN * 2.2)
        elif anchor == "top":
            group.shift(UP * 1.5)
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

        self._clear_pointer()
        if self.array_anchor == "bottom" or self.named_pointers is not None:
            self.play(*animations)
            self.wait(0.5)
            return
        target = self.array_boxes[index].get_bottom() + DOWN * 0.2
        self.pointer = Arrow(start=target + DOWN * 0.8, end=target, color=YELLOW, buff=0.05)
        pointer_label = Text(str(label or f"i = {{index}}"), font_size=24, color=YELLOW)
        pointer_label.next_to(self.pointer, DOWN, buff=0.1)
        self.pointer = VGroup(self.pointer, pointer_label)

        self.play(*animations, GrowArrow(self.pointer[0]), FadeIn(self.pointer[1]))
        self.wait(0.7)

    def _show_pointers(self, pointers):
        # Named index variables (i, left, right...) as arrows under their cells.
        if not self.array_boxes:
            return
        for name in pointers:
            if name not in self.pointer_order:
                self.pointer_order.append(name)
        colors = [YELLOW, ORANGE, PINK, TEAL, GREEN, PURPLE]
        group = VGroup()
        stacked = {{}}
        for name in self.pointer_order:
            index = pointers.get(name)
            if index is None or not (0 <= int(index) < len(self.array_boxes)):
                continue
            index = int(index)
            depth = stacked.get(index, 0)
            stacked[index] = depth + 1
            color = colors[self.pointer_order.index(name) % len(colors)]
            box = self.array_boxes[index]
            tip = box.get_bottom() + DOWN * 0.1
            arrow = Arrow(tip + DOWN * (0.7 + depth * 0.45), tip, color=color, buff=0, stroke_width=4, max_tip_length_to_length_ratio=0.25)
            label = Text(name, font_size=22, color=color).next_to(arrow, DOWN, buff=0.05)
            group.add(VGroup(arrow, label))
        if self.named_pointers is not None and len(self.named_pointers) == len(group):
            self.play(Transform(self.named_pointers, group), run_time=0.5)
        else:
            if self.named_pointers is not None:
                self.remove(self.named_pointers)
            self.named_pointers = group
            self.play(FadeIn(group), run_time=0.4)

    def _show_collection(self, name, values, kind, caption):
        # A second, smaller row for another container the code builds.
        if caption:
            self._show_caption(caption)
        tag = Text(f"{{kind}} {{name}}", font_size=22, color=TEAL)
        cells = VGroup()
        for value in values[:16]:
            box = RoundedRectangle(width=0.75, height=0.6, corner_radius=0.08, color=TEAL, fill_opacity=0.2)
            label = Text(str(value), font_size=22, color=WHITE)
            if label.width > 0.65:
                label.scale_to_fit_width(0.65)
            cells.add(VGroup(box, label.move_to(box.get_center())))
        cells.arrange(RIGHT, buff=0.1)
        if not values:
            cells = VGroup(Text("(empty)", font_size=22, color=GRAY_B))
        group = VGroup(tag, cells).arrange(RIGHT, buff=0.3)
        if group.width > 12.5:
            group.scale_to_fit_width(12.5)
        group.move_to(DOWN * 1.2 if self.array_anchor == "top" else UP * 2.6)
        if self.collection_group is not None:
            self.play(ReplacementTransform(self.collection_group, group), run_time=0.6)
        else:
            self.play(FadeIn(group, shift=UP * 0.1))
        self.collection_group = group
        self.wait(0.4)

    def _compare_value(self, index, caption):
        if not self.array_boxes:
            return
        if caption:
            self._show_caption(caption)
        i = max(0, min(int(index), len(self.array_boxes) - 1))
        self.play(*[
            box.animate.set_color(ORANGE if j == i else BLUE).set_fill(ORANGE if j == i else BLUE, opacity=0.45 if j == i else 0.15)
            for j, box in enumerate(self.array_boxes)
        ])
        self.wait(0.5)

    def _highlight_indices(self, indices, caption):
        if not self.array_boxes:
            return
        if caption:
            self._show_caption(caption)
        chosen = {{int(i) for i in indices if 0 <= int(i) < len(self.array_boxes)}}
        self.play(*[
            box.animate.set_color(YELLOW if i in chosen else BLUE).set_fill(YELLOW if i in chosen else BLUE, opacity=0.45 if i in chosen else 0.15)
            for i, box in enumerate(self.array_boxes)
        ])
        self.wait(0.5)

    def _clear_pointer(self):
        # The arrow and its label were added to the scene individually, so
        # removing only their VGroup would leave both on screen.
        if self.pointer:
            self.remove(*self.pointer.submobjects, self.pointer)
            self.pointer = None

    def _compare_indices(self, index, other, caption):
        if not self.array_boxes:
            return
        self._clear_pointer()
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
        if caption:
            self._show_caption(caption)
        count = len(self.array_boxes)
        i, j = int(index), int(other)
        if not values or len(values) != count or not (0 <= i < count and 0 <= j < count) or i == j:
            if values:
                self._create_array(values)
            return
        li, lj = self.array_labels[i], self.array_labels[j]
        self.play(
            li.animate(path_arc=PI / 2).move_to(self.array_boxes[j].get_center()),
            lj.animate(path_arc=PI / 2).move_to(self.array_boxes[i].get_center()),
            self.array_boxes[i].animate.set_color(GREEN).set_fill(GREEN, opacity=0.35),
            self.array_boxes[j].animate.set_color(GREEN).set_fill(GREEN, opacity=0.35),
        )
        self.array_labels[i], self.array_labels[j] = lj, li
        self.array_values = [str(v) for v in values]
        self.play(*[b.animate.set_color(BLUE).set_fill(BLUE, opacity=0.15) for b in (self.array_boxes[i], self.array_boxes[j])])

    def _set_index(self, index, values, caption):
        if not self.array_boxes or len(values) != len(self.array_boxes):
            self._create_array(values, caption=caption)
            return
        if caption:
            self._show_caption(caption)
        i = max(0, min(int(index), len(self.array_boxes) - 1))
        box = self.array_boxes[i]
        old = self.array_labels[i]
        new = Text(str(values[i]), font_size=36, color=WHITE)
        if self.array_group is not None and self.array_group.width > 0:
            new.scale(box.width / 1.3)  # follow the array's fit-to-frame scaling
        new.move_to(box.get_center())
        if new.width > box.width * 0.9:
            new.scale_to_fit_width(box.width * 0.9)
        self.play(Transform(old, new), box.animate.set_color(GREEN).set_fill(GREEN, opacity=0.45))
        self.array_values = [str(v) for v in values]
        self.play(box.animate.set_color(BLUE).set_fill(BLUE, opacity=0.15), run_time=0.4)

    def _show_tree(self, tree, layout=None):
        self._clear_tree()
        self.tree_nodes = {{}}
        self.tree_edges = VGroup()

        positions = {{}}
        if isinstance(layout, dict) and layout:
            for value, point in layout.items():
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    positions[str(value)] = (float(point[0]), float(point[1]))
        if not positions:
            self._assign_tree_positions(tree, 0, 0, 2.8, positions)
        positions = self._normalize_tree_positions(positions)
        nodes_group = VGroup()
        edges_group = VGroup()

        for value, (x, y) in positions.items():
            circle = Circle(radius=0.45, color=BLUE, fill_opacity=0.2)
            label = Text(str(value), font_size=30, color=WHITE)
            label.move_to(circle.get_center())
            node = VGroup(circle, label)
            node.move_to(RIGHT * x + UP * y)
            self.tree_nodes[str(value)] = node
            self._tree_objects.append(circle)
            self._tree_objects.append(label)
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
        self._tree_objects.append(edges_group)
        self.wait(0.6)

    def _normalize_tree_positions(self, positions):
        if not positions:
            return positions
        xs = [p[0] for p in positions.values()]
        ys = [p[1] for p in positions.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        def _map(v, lo, hi, tlo, thi):
            if hi - lo < 1e-6:
                return (tlo + thi) / 2.0
            return tlo + (v - lo) * (thi - tlo) / (hi - lo)

        normalized = {{}}
        for value, (x, y) in positions.items():
            nx = _map(x, min_x, max_x, -6.2, 6.2)
            ny = _map(y, min_y, max_y, -2.2, 2.6)
            normalized[str(value)] = (nx, ny)
        return normalized

    def _clear_tree(self):
        targets = [m for m in getattr(self, "_tree_objects", []) if m in self.mobjects]
        if targets:
            self.play(FadeOut(*targets))
            self.remove(*targets)
        self._tree_objects = []
        self.tree_nodes = {{}}

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
        if key in getattr(self, "graph_nodes", {{}}):
            if caption:
                self._show_caption(caption)
            anims = []
            previous = self.current_graph_node
            if previous is not None and previous in self.graph_nodes and previous != key:
                anims.append(self.graph_nodes[previous][0].animate.set_color(GREEN).set_fill(GREEN, opacity=0.35))
            anims.append(self.graph_nodes[key][0].animate.set_color(YELLOW).set_fill(YELLOW, opacity=0.5))
            self.current_graph_node = key
            self.play(*anims)
            self.wait(0.4)
            return
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
            self._graph_objects.append(circle)
            self._graph_objects.append(label)
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

    def _clear_graph(self):
        targets = [m for m in getattr(self, "_graph_objects", []) if m in self.mobjects]
        if targets:
            self.play(FadeOut(*targets))
            self.remove(*targets)
        self._graph_objects = []
        self.graph_nodes = {{}}
        self.graph_edges = {{}}
        self.graph_group = None

    def _render_graph(self, scene, caption=None):
        if caption:
            self._show_caption(caption)
        self._clear_graph()

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
        if self.array_anchor == "top" and self.array_boxes:
            self._show_variable_row(variables)
            return
        lines = [f"{{name}} = {{value}}" for name, value in variables.items()]
        text = "\\n".join(lines)
        panel = VGroup()
        bg = RoundedRectangle(width=4.5, height=0.8 + 0.45 * len(lines), corner_radius=0.15, color=BLUE_D, fill_opacity=0.35)
        label = Text(text, font_size=28, color=WHITE, line_spacing=1.1)
        label.move_to(bg.get_center())
        panel.add(bg, label)
        panel.to_edge(RIGHT, buff=0.5)
        if self.var_panel:
            self.play(Transform(self.var_panel, panel), run_time=0.5)
        else:
            self.var_panel = panel
            self.play(FadeIn(panel))

    def _show_variable_row(self, variables):
        items = [f"{{name}} = {{value}}" for name, value in variables.items()]
        rows = [items[i:i + 4] for i in range(0, len(items), 4)][:2]
        text = Text("\\n".join("     ".join(row) for row in rows), font_size=24, color=WHITE, line_spacing=1.2)
        if text.width > 12:
            text.scale_to_fit_width(12)
        bg = RoundedRectangle(width=text.width + 0.6, height=text.height + 0.4, corner_radius=0.12, color=BLUE_D, fill_opacity=0.35)
        panel = VGroup(bg, text.move_to(bg.get_center())).move_to(DOWN * 2.35)
        if self.var_panel is not None:
            self.play(Transform(self.var_panel, panel), run_time=0.4)
        else:
            self.var_panel = panel
            self.play(FadeIn(panel), run_time=0.4)

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
        self._clear_hashmap()
        self.hashmap_name = name
        self.hashmap_entries = {{}}
        for entry in entries or []:
            if isinstance(entry, (list, tuple)) and entry:
                self.hashmap_entries[str(entry[0])] = str(entry[1]) if len(entry) > 1 else ""
        self.hashmap_group = self._hashmap_table(None)
        self.play(FadeIn(self.hashmap_group, shift=DOWN * 0.1))
        self.wait(0.4)

    def _hashmap_table(self, changed_key):
        header = Text(f"hash_map: {{self.hashmap_name}}", font_size=28, color=TEAL)
        items = list(self.hashmap_entries.items())
        capacity = 12
        hidden = max(0, len(items) - capacity)
        if hidden:
            # Keep the most recently touched entries in view.
            keep = [kv for kv in items if kv[0] == changed_key]
            items = [kv for kv in items if kv[0] != changed_key][-(capacity - 1 - len(keep)):] + keep
        columns = 1 if len(items) <= 6 else 2
        width = 6.0 if columns == 1 else 3.6
        cells = VGroup()
        for i, (key, val) in enumerate(items):
            color = GREEN if key == changed_key else TEAL
            box = RoundedRectangle(width=width, height=0.48, corner_radius=0.08, color=color, fill_opacity=0.3 if key == changed_key else 0.15)
            text = Text(f"{{key}}  →  {{val}}", font_size=20, color=WHITE, font="Consolas")
            if text.width > width * 0.9:
                text.scale_to_fit_width(width * 0.9)
            cell = VGroup(box, text.move_to(box.get_center()))
            col, row = (0, i) if columns == 1 else (i // 6, i % 6)
            cell.move_to(RIGHT * col * (width + 0.2) + DOWN * row * 0.56)
            cells.add(cell)
        if not items:
            cells.add(Text("(empty)", font_size=22, color=GRAY_B))
        cells.next_to(header, DOWN, buff=0.25, aligned_edge=LEFT)
        group = VGroup(header, cells)
        if hidden:
            group.add(Text(f"+{{hidden}} more", font_size=20, color=GRAY_B).next_to(cells, DOWN, buff=0.1, aligned_edge=LEFT))
        group.to_edge(UP, buff=0.6).to_edge(LEFT, buff=0.6)
        return group

    def _clear_hashmap(self):
        if self.hashmap_group is not None and self.hashmap_group in self.mobjects:
            self.play(FadeOut(self.hashmap_group))
            self.remove(self.hashmap_group)
        self.hashmap_group = None

    def _hashmap_insert(self, name, label, caption, values=None):
        if caption:
            self._show_caption(caption)
        if not values or self.hashmap_group is None:
            return
        key, val = str(values[0][0]), str(values[0][1])
        self.hashmap_entries[key] = val
        table = self._hashmap_table(key)
        self.play(ReplacementTransform(self.hashmap_group, table), run_time=0.6)
        self.hashmap_group = table
        self.wait(0.3)

    def _show_heap(self, values, caption):
        if caption:
            self._show_caption(caption)
        self._clear_heap()
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
        self._heap_objects = [title, edges] + [n[0] for n in nodes] + [n[1] for n in nodes]
        self.wait(0.8)

    def _clear_heap(self):
        targets = [m for m in getattr(self, "_heap_objects", []) if m in self.mobjects]
        if targets:
            self.play(FadeOut(*targets))
            self.remove(*targets)
        self._heap_objects = []

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

    def _show_chapter(self, text):
        if not text:
            return
        banner = RoundedRectangle(width=11, height=0.9, corner_radius=0.15, color=YELLOW, fill_opacity=0.25)
        label = Text(str(text), font_size=34, color=YELLOW, font="Consolas", weight=BOLD)
        label.move_to(banner.get_center())
        group = VGroup(banner, label)
        self.play(FadeIn(group, scale=0.92))
        self.wait(1.0)
        self.play(FadeOut(group))

    def _show_architecture(self, components, connections, layout, caption):
        if caption:
            self._show_caption(caption)
        self._clear_architecture()
        fills = {{
            "client": BLUE,
            "gateway": PURPLE,
            "service": TEAL,
            "queue": GREEN,
            "cache": YELLOW,
            "database": ORANGE,
            "other": GRAY,
        }}
        boxes = {{}}
        group = VGroup()
        for comp in components:
            cid = str(comp.get("id"))
            label = str(comp.get("label") or cid)
            category = str(comp.get("category") or "other")
            box = RoundedRectangle(width=2.4, height=0.95, corner_radius=0.12, color=fills.get(category, GRAY), fill_opacity=0.3)
            text = Text(label, font_size=20, color=WHITE).move_to(box.get_center())
            item = VGroup(box, text)
            if cid in layout and isinstance(layout[cid], (list, tuple)) and len(layout[cid]) >= 2:
                item.move_to(RIGHT * float(layout[cid][0]) + UP * float(layout[cid][1]))
            boxes[cid] = item
            group.add(item)
            self._arch_objects.append(item)

        connections_group = VGroup()
        for conn in connections:
            source = str(conn.get("from"))
            target = str(conn.get("to"))
            if source in boxes and target in boxes:
                line = Line(boxes[source].get_center(), boxes[target].get_center(), color=GRAY_B, stroke_width=3)
                connections_group.add(line)
                self.arch_connections[(source, target)] = line
                self.arch_connections[(target, source)] = line
        if len(connections_group) > 0:
            self._arch_objects.append(connections_group)

        self.arch_components = boxes
        self.play(Create(connections_group), LaggedStart(*[FadeIn(item, scale=0.9, shift=UP * 0.2) for item in group], lag_ratio=0.12))
        self.wait(0.8)

    def _clear_architecture(self):
        targets = [m for m in self._arch_objects if m in self.mobjects]
        if targets:
            self.play(FadeOut(*targets))
            self.remove(*targets)
        self._arch_objects = []
        self.arch_components = {{}}
        self.arch_connections = {{}}

    def _show_flow(self, source, target, caption):
        if caption:
            self._show_caption(caption)
        if source is not None and target is not None:
            key = (str(source), str(target))
            info = self.arch_connections.get(key)
            if info:
                arrow = Arrow(
                    info.get_start(),
                    info.get_end(),
                    color=ORANGE,
                    buff=0.0,
                    stroke_width=5,
                    max_tip_length_to_length_ratio=0.12,
                )
                self.play(Create(arrow), info.animate.set_color(ORANGE).set_stroke(width=5))
                self.wait(0.6)
                self.play(FadeOut(arrow), info.animate.set_color(GRAY_B).set_stroke(width=3))
            else:
                self._show_caption(f"flow {{source}} → {{target}}")
        self.wait(0.4)

    def _show_grid(self, values, caption):
        if caption:
            self._show_caption(caption)
        if self.grid_group is not None:
            self.play(FadeOut(self.grid_group))
        rows = len(values)
        cols = max((len(r) for r in values), default=0)
        if not rows or not cols:
            return
        cell = min(1.0, 5.2 / rows, 11.0 / cols)
        self.grid_cells = {{}}
        self.grid_highlight = None
        group = VGroup()
        for r, row in enumerate(values):
            for c, value in enumerate(row):
                box = Square(side_length=cell * 0.94, color=BLUE, fill_opacity=0.15)
                label = Text(str(value), font_size=max(14, int(30 * cell)), color=WHITE)
                if label.width > box.width * 0.85:
                    label.scale_to_fit_width(box.width * 0.85)
                item = VGroup(box, label.move_to(box.get_center()))
                item.move_to(RIGHT * (c - (cols - 1) / 2) * cell + UP * ((rows - 1) / 2 - r) * cell)
                self.grid_cells[(r, c)] = item
                group.add(item)
        group.shift(UP * 0.4)
        self.grid_group = group
        self.play(FadeIn(group, lag_ratio=0.02))
        self.wait(0.4)

    def _set_cell(self, row, col, values, caption):
        if caption:
            self._show_caption(caption)
        item = self.grid_cells.get((int(row), int(col)))
        if item is None:
            self._show_grid(values, None)
            return
        box, old = item[0], item[1]
        new = Text(str(values[int(row)][int(col)]), font_size=max(14, int(30 * box.width / 0.94)), color=WHITE)
        if new.width > box.width * 0.85:
            new.scale_to_fit_width(box.width * 0.85)
        new.move_to(box.get_center())
        self.play(Transform(old, new), box.animate.set_color(GREEN).set_fill(GREEN, opacity=0.45))
        self.play(box.animate.set_color(TEAL).set_fill(TEAL, opacity=0.3), run_time=0.3)

    def _highlight_cell(self, row, col, caption):
        if caption:
            self._show_caption(caption)
        item = self.grid_cells.get((int(row), int(col)))
        if item is None:
            return
        anims = []
        if self.grid_highlight is not None and self.grid_highlight is not item:
            anims.append(self.grid_highlight[0].animate.set_stroke(BLUE, width=4))
        anims.append(item[0].animate.set_stroke(YELLOW, width=8))
        self.grid_highlight = item
        self.play(*anims, run_time=0.5)

    def _show_linked_list(self, nodes, edges, pointers, caption):
        if caption:
            self._show_caption(caption)
        count = len(nodes)
        if not count:
            return
        spacing = min(2.2, 12.0 / max(count, 1))
        boxes = []
        group = VGroup()
        for i, value in enumerate(nodes):
            box = RoundedRectangle(width=1.1, height=0.8, corner_radius=0.1, color=BLUE, fill_opacity=0.2)
            label = Text(str(value), font_size=30, color=WHITE).move_to(box.get_center())
            node = VGroup(box, label).move_to(RIGHT * (i - (count - 1) / 2) * spacing + UP * 0.6)
            boxes.append(node)
            group.add(node)
        for edge in edges:
            a, b = int(edge["from"]), int(edge["to"])
            if not (0 <= a < count and 0 <= b < count) or a == b:
                continue
            if b == a + 1:
                arrow = Arrow(boxes[a].get_right(), boxes[b].get_left(), buff=0.05, color=GRAY_B, stroke_width=3)
            else:
                start, end = boxes[a].get_top(), boxes[b].get_top()
                arrow = CurvedArrow(start, end, angle=-PI / 2.5 if b > a else PI / 2.5, color=ORANGE)
            group.add(arrow)
        below = {{}}
        null_names = []
        for name, index in (pointers or {{}}).items():
            if index is None or not (0 <= int(index) < count):
                null_names.append(name)
                continue
            depth = below.get(int(index), 0)
            below[int(index)] = depth + 1
            tag = Text(str(name), font_size=24, color=YELLOW)
            tag.next_to(boxes[int(index)], DOWN, buff=0.35 + depth * 0.4)
            group.add(tag)
        if null_names:
            group.add(Text(", ".join(null_names) + " = null", font_size=24, color=GRAY_B).to_edge(LEFT, buff=0.6).shift(DOWN * 1.6))
        if self.ll_group is not None:
            self.play(ReplacementTransform(self.ll_group, group), run_time=0.8)
        else:
            self.play(FadeIn(group))
        self.ll_group = group
        self.wait(0.4)

    def _highlight_component(self, component, caption):
        if caption:
            self._show_caption(caption)
        if component is not None:
            item = self.arch_components.get(str(component))
            if item is not None:
                self.play(item[0].animate.set_color(YELLOW).set_fill(YELLOW, opacity=0.65).scale(1.08))
                self.wait(0.6)
                self.play(item[0].animate.set_fill(item[0].get_color(), opacity=0.3).scale(1 / 1.08))
        self.wait(0.4)
"""
