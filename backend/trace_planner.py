"""Turn an execution trace into an animation plan.

Nothing here knows algorithm names. Views are chosen from the SHAPE of the
data the program held (a list of scalars is an array, objects with two
self-references form a tree, a container mapping nodes to neighbor lists is a
graph), and events are derived from what CHANGED between consecutive steps
(two cells exchanged values -> swap; a list grew at its end -> push).

Source lines are consulted for one thing only: which array cells a line reads
(`a[j] > a[j + 1]`), with index expressions evaluated against the real values
of the locals at that step.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# Safety valve only: the renderer speeds up long plans instead of cutting them.
MAX_EVENTS = 1500
INFINITY_THRESHOLD = 2**31 - 1
SCALAR_TYPES = (int, float, str, bool, type(None))

Step = dict[str, Any]


# ---------------------------------------------------------------- entry point


def plan_from_trace(trace: dict[str, Any], code: str) -> dict[str, Any] | None:
    """Return a scene plan, or None when the trace has nothing to show."""
    steps = trace.get("steps") or []
    if not steps:
        return None

    ctx = TraceContext(steps=steps, lines=code.splitlines(), language=trace.get("language", ""))
    view = _choose_view(ctx)
    builder = SceneBuilder()

    builder.add("show_title", text=_title(ctx, view))
    driver = trace.get("driver")
    if driver:
        builder.add("show_caption", text=driver["description"])

    VIEW_BUILDERS[view.kind](ctx, view, builder)
    result = _entry_result(ctx)
    if result:
        builder.add("show_caption", text=result)

    if trace.get("truncated"):
        builder.add("show_caption", text="Trace stopped at the step limit")
    if trace.get("error"):
        builder.add("show_caption", text=f"Program stopped: {trace['error'][:80]}")

    scenes = builder.finish()
    if not any(s["action"] not in {"show_title", "show_caption"} for s in scenes):
        return None
    return {
        "algorithm": None,
        "title": _title(ctx, view),
        "data_structure": view.kind,
        "description": f"Execution trace of your code shown as a {view.kind.replace('_', ' ')}",
        "scenes": scenes,
    }


# ------------------------------------------------------------------- context


@dataclass
class TraceContext:
    steps: list[Step]
    lines: list[str]
    language: str
    _names: dict[str, Counter] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for step in self.steps:
            for frame in step["stack"]:
                for name, value in frame["locals"].items():
                    ref = _ref(value)
                    if ref:
                        self._names.setdefault(ref, Counter())[name] += 1

    def source(self, line: int) -> str:
        if 1 <= line <= len(self.lines):
            return self.lines[line - 1]
        return ""

    def name_of(self, ref: str, step: Step | None = None) -> str:
        if step:
            for frame in reversed(step["stack"]):
                for name, value in frame["locals"].items():
                    if _ref(value) == ref:
                        return name
        names = self._names.get(ref)
        return names.most_common(1)[0][0] if names else "data"

    def all_names(self, ref: str) -> set[str]:
        return set(self._names.get(ref, ()))

    def objects(self) -> dict[str, list[tuple[int, dict[str, Any]]]]:
        """Every heap object's snapshots, keyed by heap id."""
        timeline: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for index, step in enumerate(self.steps):
            for ref, obj in step["heap"].items():
                timeline.setdefault(ref, []).append((index, obj))
        return timeline

    def user_functions(self) -> Counter:
        return Counter(
            s["func"]
            for s in self.steps
            if s["func"] not in {"<module>", "<static>"}
            and not _is_constructor(s["func"])
            and not _is_anonymous(s["func"])
            and not (s["func"] == "main" and self.language in {"java", "cpp"})
        )


@dataclass
class View:
    kind: str
    ref: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class SceneBuilder:
    def __init__(self) -> None:
        self.scenes: list[dict[str, Any]] = []
        self.dropped = 0

    def add(self, action: str, **fields: Any) -> None:
        if len(self.scenes) >= MAX_EVENTS:
            self.dropped += 1
            return
        scene = {"action": action}
        scene.update({k: v for k, v in fields.items() if v is not None})
        self.scenes.append(scene)

    def finish(self) -> list[dict[str, Any]]:
        if self.dropped:
            self.scenes.append(
                {"action": "show_caption", "text": f"… {self.dropped} more steps not shown"}
            )
        return self.scenes


# ------------------------------------------------------------ view selection


def _choose_view(ctx: TraceContext) -> View:
    objects = ctx.objects()

    node_classes = _node_classes(objects)
    for cls, info in node_classes.items():
        if len(info["self_fields"]) >= 2 and info["count"] >= 2:
            return View("tree", extra={"class": cls, **info})
    for cls, info in node_classes.items():
        if len(info["self_fields"]) == 1 and info["count"] >= 2:
            return View("linked_list", extra={"class": cls, **info})

    graph = _find_graph(ctx, objects)
    if graph:
        return graph

    grid = _find_grid(ctx, objects)
    if grid:
        return grid

    mutations = {
        ref: _mutation_count(snaps)
        for ref, snaps in objects.items()
        # Tuples are value slots (a C++ pair inside a container buffer), not arrays.
        if (_is_scalar_list(snaps) and snaps[-1][1].get("kind") == "list")
        or snaps[-1][1].get("kind") == "dict"
    }
    mutated = [ref for ref, count in mutations.items() if count > 0]
    if mutated:
        best = max(mutated, key=lambda r: (mutations[r], _is_scalar_list(objects[r])))
        snaps = objects[best]
        if snaps[-1][1].get("kind") == "dict":
            return View("hashmap", best, {"inputs": _input_arrays(ctx, objects, best)})
        if _behaves_like_stack(snaps):
            return View("stack", best, {"end": _stack_end(snaps)})
        if _is_recursive(ctx) and not _shared_across_recursion(ctx, best):
            # Each call builds its own lists (e.g. merge sort): the story is
            # the calls and what they return, not any single list.
            return View("call_stack")
        return View("array", best)

    if _is_recursive(ctx):
        return View("call_stack")

    read_arrays = [
        ref
        for ref, snaps in objects.items()
        if _is_scalar_list(snaps) and snaps[-1][1].get("kind") == "list" and len(_items(snaps[-1][1])) > 1
    ]
    if read_arrays:
        best = max(read_arrays, key=lambda r: _read_count(ctx, r))
        return View("array", best)

    if len(ctx.user_functions()) > 0 and any(s["event"] == "call" for s in ctx.steps):
        return View("call_stack")
    return View("variables")


def _node_classes(objects: dict[str, list]) -> dict[str, dict[str, Any]]:
    """Classes whose instances point at other instances of the same class."""
    classes: dict[str, dict[str, Any]] = {}
    ref_class = {
        ref: snaps[-1][1].get("class")
        for ref, snaps in objects.items()
        if snaps[-1][1].get("kind") == "object"
    }
    for ref, cls in ref_class.items():
        info = classes.setdefault(cls, {"count": 0, "self_fields": [], "value_field": None})
        info["count"] += 1
        for _index, obj in objects[ref]:
            for name, value in (obj.get("fields") or {}).items():
                target = _ref(value)
                if target and ref_class.get(target) == cls and name not in info["self_fields"]:
                    info["self_fields"].append(name)
                elif (
                    info["value_field"] is None
                    and isinstance(value, (int, float, str))
                    and not isinstance(value, bool)
                ):
                    info["value_field"] = name
    # Keep declaration order (left before right) using the first instance.
    for cls, info in classes.items():
        sample = next(
            (objects[r][-1][1] for r, c in ref_class.items() if c == cls), {}
        )
        order = list((sample.get("fields") or {}).keys())
        info["self_fields"].sort(key=lambda f: order.index(f) if f in order else len(order))
    return {cls: info for cls, info in classes.items() if info["self_fields"]}


def _find_graph(ctx: TraceContext, objects: dict[str, list]) -> View | None:
    best: tuple[int, str, int, list] | None = None
    for ref, snaps in objects.items():
        for index, obj in snaps:
            adjacency = _as_adjacency(obj, ctx.steps[index]["heap"])
            if adjacency is None:
                continue
            edge_count = sum(len(v) for v in adjacency.values())
            if edge_count and (best is None or edge_count > best[0]):
                best = (edge_count, ref, index, adjacency)
    if best is None:
        return None
    _count, ref, index, adjacency = best
    return View("graph", ref, {"adjacency": adjacency, "built_at": index})


def _as_adjacency(obj: dict[str, Any], heap: dict[str, Any]) -> dict[Any, list] | None:
    """Read a container as {node: [(neighbor, weight), ...]} if it is one."""
    if obj.get("kind") == "dict":
        rows = [(k, v) for k, v in obj.get("entries") or []]
    elif obj.get("kind") == "list":
        rows = list(enumerate(obj.get("items") or []))
    else:
        return None
    if len(rows) < 2:
        return None

    keys = {k for k, _v in rows}
    adjacency: dict[Any, list] = {}
    for key, value in rows:
        target = heap.get(_ref(value) or "", {})
        if target.get("kind") not in {"list", "set", "tuple"}:
            return None
        neighbors = []
        for item in target.get("items") or []:
            neighbor, weight = _neighbor_entry(item, heap)
            if neighbor is None or neighbor not in keys:
                return None
            neighbors.append((neighbor, weight))
        if len({n for n, _w in neighbors}) != len(neighbors):
            return None  # a repeated "neighbor" means this is a matrix row, not a neighbor list
        adjacency[key] = neighbors
    return adjacency


def _neighbor_entry(item: Any, heap: dict[str, Any]) -> tuple[Any, Any]:
    if isinstance(item, (int, str)) and not isinstance(item, bool):
        return item, None
    pair = heap.get(_ref(item) or "", {})
    values = pair.get("items") or []
    if pair.get("kind") in {"list", "tuple"} and 1 <= len(values) <= 3:
        if all(isinstance(v, (int, float, str)) and not isinstance(v, bool) for v in values):
            return values[0], values[1] if len(values) > 1 else None
    return None, None


def _input_arrays(ctx: TraceContext, objects: dict[str, list], exclude: str) -> list[str]:
    return [
        ref
        for ref, snaps in objects.items()
        if ref != exclude and _is_scalar_list(snaps) and _mutation_count(snaps) == 0
        and len(_items(snaps[-1][1])) > 1
    ][:1]


def _stack_end(snaps: list[tuple[int, dict]]) -> str | None:
    """'back' or 'front' if the list only ever grows/shrinks at that one end
    and is popped at least once; None otherwise."""
    pops = 0
    end = None
    previous = _items(snaps[0][1])
    for _index, obj in snaps[1:]:
        current = _items(obj)
        if current == previous:
            continue
        if len(current) == len(previous) + 1:
            side = "back" if current[:-1] == previous else "front" if current[1:] == previous else None
        elif len(current) == len(previous) - 1:
            side = "back" if current == previous[:-1] else "front" if current == previous[1:] else None
            pops += 1
        else:
            return None
        if side is None or (end is not None and side != end):
            return None
        end = side
        previous = current
    return end if pops else None


def _behaves_like_stack(snaps: list[tuple[int, dict]]) -> bool:
    return _stack_end(snaps) is not None


def _is_recursive(ctx: TraceContext) -> bool:
    for step in ctx.steps:
        funcs = [f["func"] for f in step["stack"] if not _is_constructor(f["func"]) and not _is_anonymous(f["func"])]
        if len(funcs) != len(set(funcs)):
            return True
    return False


def _shared_across_recursion(ctx: TraceContext, ref: str) -> bool:
    """True when two frames of the same function see this object at once."""
    for step in ctx.steps:
        holders = Counter(
            frame["func"]
            for frame in step["stack"]
            if any(_ref(v) == ref for v in frame["locals"].values())
        )
        if holders and holders.most_common(1)[0][1] >= 2:
            return True
    return False


def _find_grid(ctx: TraceContext, objects: dict[str, list]) -> View | None:
    """A rectangular list of scalar rows that the program writes or indexes twice."""
    best: tuple[int, str] | None = None
    for ref, snaps in objects.items():
        index, obj = snaps[-1]
        rows = _grid_rows(obj, ctx.steps[index]["heap"])
        if rows is None:
            continue
        names = ctx.all_names(ref)
        double_indexed = any(
            re.search(rf"(?<![\w.]){re.escape(n)}\s*\[[^\]]+\]\s*\[", line)
            for n in names
            for line in ctx.lines
        )
        changes = _grid_changes(ctx, ref)
        if not (double_indexed or changes):
            continue
        score = changes * 10 + len(rows)
        if best is None or score > best[0]:
            best = (score, ref)
    return View("grid", best[1]) if best else None


def _grid_rows(obj: dict[str, Any], heap: dict[str, Any]) -> list[list] | None:
    if obj.get("kind") not in {"list", "tuple"}:
        return None
    rows = []
    for item in obj.get("items") or []:
        row = heap.get(_ref(item) or "", {})
        values = row.get("items")
        if row.get("kind") not in {"list", "tuple"} or not values or not _all_scalars(values):
            return None
        rows.append(values)
    if len(rows) < 2 or len({len(r) for r in rows}) != 1:
        return None
    return rows


def _grid_at(step: Step, ref: str) -> list[list] | None:
    obj = step["heap"].get(ref)
    return _grid_rows(obj, step["heap"]) if obj else None


def _grid_changes(ctx: TraceContext, ref: str) -> int:
    changes, previous = 0, None
    for step in ctx.steps:
        rows = _grid_at(step, ref)
        if rows is None:
            continue
        if previous is not None and rows != previous:
            changes += 1
        previous = rows
    return changes


def _read_count(ctx: TraceContext, ref: str) -> int:
    names = ctx.all_names(ref)
    return sum(
        1
        for step in ctx.steps
        if any(re.search(rf"(?<![\w.]){re.escape(n)}\s*[\[.]", ctx.source(step["line"])) for n in names)
    )


# ---------------------------------------------------------------- array view


def _build_array(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    ref = view.ref
    previous: list | None = None
    last_highlight: tuple | None = None
    index_vars = _index_variables(ctx, ctx.all_names(ref))
    last_pointers: dict | None = None
    last_scalars: dict | None = None
    shown_collections: dict[str, list] = {}

    for index, step in enumerate(ctx.steps):
        items = _items_at(step, ref)
        if items is None:
            continue
        name = ctx.name_of(ref, step)
        display = [_display(v) for v in items]

        if previous is None:
            out.add("create_array", values=display, layout={"anchor": "top"}, caption=f"{name} = {_fmt_list(display)}")
        elif items != previous:
            _emit_array_diff(out, name, previous, items, display)
            last_highlight = None
        previous = items

        frame = _frame_holding(step, ref) or (step["stack"][-1] if step["stack"] else None)
        if frame is not None and not _is_constructor(frame["func"]):
            pointers = {
                var: frame["locals"][var]
                for var in index_vars
                if _is_int(frame["locals"].get(var)) and 0 <= frame["locals"][var] < len(items)
            }
            if pointers != last_pointers and (pointers or last_pointers):
                out.add("show_pointers", variables=pointers)
                last_pointers = pointers
            scalars = {
                k: _display(v)
                for k, v in frame["locals"].items()
                if isinstance(v, SCALAR_TYPES) and k not in index_vars
            }
            if scalars and scalars != last_scalars:
                _emit_derived_values(ctx, index, name, items, scalars, last_scalars or {}, out)
                out.add("show_variables", variables=scalars)
                last_scalars = scalars
            _emit_side_collections(step, frame, ref, shown_collections, out)

        following = _items_at(ctx.steps[index + 1], ref) if index + 1 < len(ctx.steps) else None
        written = (
            {i for i, (a, b) in enumerate(zip(items, following)) if a != b}
            if following is not None and len(following) == len(items)
            else set()
        )
        last_highlight = _emit_reads(ctx, step, ref, name, items, out, last_highlight, written)


def _emit_derived_values(
    ctx: TraceContext, index: int, name: str, items: list, scalars: dict, before: dict, out: SceneBuilder
) -> None:
    """`mini = *min_element(nums...)`: point at the element a new value came from."""
    if index == 0:
        return
    line = _strip_comment(ctx.source(ctx.steps[index - 1]["line"]))
    if not re.search(rf"(?<![\w.]){re.escape(name)}\b(?!\s*\[)", line):
        return
    shown = [_display(v) for v in items]
    for var, value in scalars.items():
        if before.get(var) == value or value not in shown:
            continue
        if not re.search(rf"\b{re.escape(var)}\s*=(?!=)", line):
            continue
        position = shown.index(value)
        out.add(
            "highlight_index",
            index=position,
            label=var,
            caption=f"{var} = {value}, which is {name}[{position}]",
        )


def _emit_side_collections(
    step: Step, frame: dict[str, Any], primary: str, shown: dict[str, list], out: SceneBuilder
) -> None:
    """Other lists/sets this function builds (e.g. a set made from the array)."""
    for var, value in frame["locals"].items():
        ref = _ref(value)
        if not ref or ref == primary:
            continue
        obj = step["heap"].get(ref, {})
        if obj.get("kind") not in {"list", "set"}:
            continue
        values = [_display(v) for v in obj.get("items") or []]
        if not _all_scalars(obj.get("items") or []) or shown.get(var) == values:
            continue
        shown[var] = values
        kind = "set" if obj.get("kind") == "set" else "list"
        out.add(
            "show_collection",
            text=var,
            values=values,
            label=kind,
            caption=f"{kind} {var} = {_fmt_list(values)}",
        )


def _emit_array_diff(
    out: SceneBuilder, name: str, before: list, after: list, display: list
) -> None:
    if len(before) != len(after):
        verb = "grows" if len(after) > len(before) else "shrinks"
        out.add("create_array", values=display, caption=f"{name} {verb}: {_fmt_list(display)}")
        return
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if len(changed) == 2 and before[changed[0]] == after[changed[1]] and before[changed[1]] == after[changed[0]]:
        i, j = changed
        out.add(
            "swap_indices",
            index=i,
            label=str(j),
            values=display,
            caption=f"Swap {name}[{i}] and {name}[{j}] → {_fmt_list(display)}",
        )
        return
    for i in changed[:3]:
        out.add(
            "set_index",
            index=i,
            values=display,
            caption=f"{name}[{i}] = {display[i]}",
        )
    if len(changed) > 3:
        out.add("create_array", values=display, caption=f"{name} = {_fmt_list(display)}")


def _emit_reads(
    ctx: TraceContext,
    step: Step,
    ref: str,
    name: str,
    items: list,
    out: SceneBuilder,
    last: tuple | None,
    written: set[int] = frozenset(),
) -> tuple | None:
    if step["event"] != "line":
        return last
    line = _strip_comment(ctx.source(step["line"]))
    aliases = _aliases(step, ref) or {name}
    reads, is_comparison = _subscript_reads(line, aliases)
    env = _scalar_env(step)
    lengths = {alias: len(items) for alias in aliases}

    indices: list[tuple[int, str]] = []
    for expr in reads:
        value = _eval_index(expr, env, lengths)
        if value is not None and 0 <= value < len(items) and value not in [i for i, _ in indices]:
            indices.append((value, expr.strip()))
    if not indices or (written and {i for i, _ in indices} <= written and not is_comparison):
        return last

    key = (step["line"], tuple(i for i, _ in indices))
    if key == last:
        return last
    shown = [_display(v) for v in items]
    if len(indices) >= 3 or (len(indices) == 2 and not is_comparison):
        verb = "Check" if is_comparison else "Read"
        out.add(
            "highlight_indices",
            values=[i for i, _ in indices],
            caption=f"{verb} " + ", ".join(f"{name}[{expr}]={shown[i]}" for i, expr in indices),
        )
    elif is_comparison and len(indices) >= 2:
        (i, _), (j, _) = indices[:2]
        out.add(
            "compare_indices",
            index=i,
            label=str(j),
            caption=f"Compare {name}[{i}]={shown[i]} with {name}[{j}]={shown[j]}",
        )
    elif is_comparison:
        i, expr = indices[0]
        out.add(
            "compare_value",
            index=i,
            label=expr if expr != str(i) else f"i={i}",
            caption=f"Compare {name}[{expr}]={shown[i]}: {_condition_with_values(line, env)}",
        )
    else:
        verb = "Read"
        i, expr = indices[0]
        out.add(
            "highlight_index",
            index=i,
            label=expr if expr != str(i) else f"i={i}",
            caption=f"{verb} {name}[{expr}] = {shown[i]}",
        )
    return key


_ASSIGN = re.compile(r"(?<![=!<>+\-*/%&|^:])=(?![=>])")
_COMPARISON = re.compile(r"<=|>=|==|!=|===|!==|(?<![<\-])<(?![<=])|(?<![>\-])>(?![>=])")


def _subscript_reads(line: str, aliases: set[str]) -> tuple[list[str], bool]:
    """Index expressions this line READS from the array, and whether it compares."""
    rhs = line
    # `if (a[j] < a[m]) m = j;` -- only the condition is read on this line's
    # test; splitting at the `=` would lose the comparison.
    condition = re.match(r"^\s*(?:\}\s*)?(?:else\s+)?(?:if|while)\s*\(", line)
    inner = _balanced(line, condition.end() - 1) if condition else None
    depth = 0 if inner is None else None
    if inner is not None:
        rhs = inner
    for pos, char in enumerate(line if depth is not None else ""):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0 and _ASSIGN.match(line, pos):
            rhs = line[pos + 1 :]
            break

    reads: list[str] = []
    for alias in aliases:
        pattern = rf"(?<![\w.]){re.escape(alias)}\s*(\[|\.get\(|\.at\()"
        for match in re.finditer(pattern, rhs):
            inner = _balanced(rhs, match.end() - 1)
            if inner is not None:
                reads.append(inner)

    cleaned = re.sub(r"->|<<|>>|=>|<\s*[\w:]+(\s*,\s*[\w:]+)*\s*>", " ", rhs)
    return reads, bool(_COMPARISON.search(cleaned))


def _condition_with_values(line: str, env: dict[str, Any]) -> str:
    """The line's test with plain variables annotated by their current values."""
    match = re.search(r"\b(?:if|while|elif)\b\s*\(?(.*)", line)
    text = (match.group(1) if match else line).strip().rstrip(":{").rstrip(")").strip()
    names = [n for n in dict.fromkeys(re.findall(r"(?<![\w.\[])([A-Za-z_]\w*)(?![\w\[(])", text)) if n in env]
    values = ", ".join(f"{n}={_display(env[n])}" for n in names[:3])
    return f"{text[:50]}" + (f"  ({values})" if values else "")


def _index_variables(ctx: TraceContext, names: set[str]) -> list[str]:
    """Plain variables the code uses directly as indexes into this array."""
    found: list[str] = []
    for line in ctx.lines:
        for name in names:
            for match in re.finditer(rf"(?<![\w.]){re.escape(name)}\s*\[\s*([A-Za-z_]\w*)\s*\]", line):
                var = match.group(1)
                if var not in found and var not in names:
                    found.append(var)
    return found


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _balanced(text: str, open_pos: int) -> str | None:
    pairs = {"[": "]", "(": ")"}
    opener = text[open_pos]
    closer = pairs.get(opener)
    if closer is None:
        return None
    depth = 0
    for pos in range(open_pos, len(text)):
        if text[pos] == opener:
            depth += 1
        elif text[pos] == closer:
            depth -= 1
            if depth == 0:
                return text[open_pos + 1 : pos]
    return None


def _eval_index(expr: str, env: dict[str, Any], lengths: dict[str, int]) -> int | None:
    text = expr.strip()
    for name, length in lengths.items():
        text = re.sub(rf"\blen\(\s*{re.escape(name)}\s*\)|\b{re.escape(name)}\s*\.\s*(length|size\(\s*\))", str(length), text)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    try:
        value = _eval_node(tree.body, env)
    except (ValueError, ZeroDivisionError, TypeError):
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _eval_node(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        value = env[node.id]
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise ValueError(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _eval_node(node.operand, env)
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp):
        left, right = _eval_node(node.left, env), _eval_node(node.right, env)
        ops = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.FloorDiv: lambda a, b: a // b,
            ast.Div: lambda a, b: int(a / b),  # C-family integer division
            ast.Mod: lambda a, b: a % b,
        }
        op = ops.get(type(node.op))
        if op:
            return op(left, right)
    raise ValueError(ast.dump(node))


# ----------------------------------------------------------------- grid view


def _build_grid(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    previous: list[list] | None = None
    last_read: tuple | None = None
    for step in ctx.steps:
        rows = _grid_at(step, view.ref)
        if rows is None:
            continue
        name = ctx.name_of(view.ref, step)
        display = [[_display(v) for v in row] for row in rows]
        if previous is None:
            out.add("show_grid", values=display, caption=f"{name}: {len(rows)} × {len(rows[0])} grid")
        elif rows != previous:
            for r, (old_row, new_row) in enumerate(zip(previous, rows)):
                for c, (a, b) in enumerate(zip(old_row, new_row)):
                    if a != b:
                        out.add("set_cell", row=r, col=c, values=display, caption=f"{name}[{r}][{c}] = {display[r][c]}")
            last_read = None
        previous = rows

        if step["event"] != "line":
            continue
        line = _strip_comment(ctx.source(step["line"]))
        env = _scalar_env(step)
        for alias in _aliases(step, view.ref) or {name}:
            for match in re.finditer(rf"(?<![\w.]){re.escape(alias)}\s*\[([^\]]+)\]\s*\[([^\]]+)\]", line):
                r = _eval_index(match.group(1), env, {})
                c = _eval_index(match.group(2), env, {})
                if r is None or c is None or not (0 <= r < len(rows) and 0 <= c < len(rows[0])):
                    continue
                key = (r, c)
                if key != last_read:
                    last_read = key
                    out.add("highlight_cell", row=r, col=c, caption=f"Check {name}[{r}][{c}] = {display[r][c]}")


# ---------------------------------------------------------------- stack view


def _build_stack(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    previous: list | None = None
    top_first = view.extra.get("end") == "front"
    for step in ctx.steps:
        items = _items_at(step, view.ref)
        if items is None:
            continue
        name = ctx.name_of(view.ref, step)
        if previous is None:
            for value in (reversed(items) if top_first else items):
                out.add("push_stack", label=str(_display(value)), caption=f"{name} starts with {_display(value)}")
        elif len(items) == len(previous) + 1:
            value = _display(items[0] if top_first else items[-1])
            out.add("push_stack", label=str(value), caption=f"Push {value} onto {name}")
        elif len(items) == len(previous) - 1:
            value = _display(previous[0] if top_first else previous[-1])
            out.add("pop_stack", label=str(value), caption=f"Pop {value} from {name}")
        previous = items
    if previous is not None:
        state = "empty" if not previous else f"holding {_fmt_list([_display(v) for v in previous])}"
        out.add("show_caption", text=f"{ctx.name_of(view.ref)} ends {state}")


# -------------------------------------------------------------- hashmap view


def _build_hashmap(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    shown_inputs: set[str] = set()
    previous: dict | None = None
    last_read: tuple | None = None
    previous_vars: dict | None = None
    for step in ctx.steps:
        for input_ref in view.extra.get("inputs", []):
            items = _items_at(step, input_ref)
            if items is None:
                continue
            input_name = ctx.name_of(input_ref, step)
            if input_ref not in shown_inputs:
                shown_inputs.add(input_ref)
                display = [_display(v) for v in items]
                out.add(
                    "create_array",
                    values=display,
                    layout={"anchor": "bottom"},
                    caption=f"Input {input_name} = {_fmt_list(display)}",
                )
            last_read = _emit_reads(ctx, step, input_ref, input_name, items, out, last_read)

        owner = _frame_holding(step, view.ref)
        if owner is not None:
            scalars = {
                k: _display(v)
                for k, v in owner["locals"].items()
                if isinstance(v, SCALAR_TYPES)
            }
            if scalars and scalars != previous_vars:
                out.add("show_variables", variables=scalars)
                previous_vars = scalars

        entries = _entries_at(step, view.ref)
        if entries is None:
            continue
        name = ctx.name_of(view.ref, step)
        if previous is None:
            out.add("show_hashmap", text=name, values=[[k, v] for k, v in entries.items()], caption=f"{name} starts with {len(entries)} entries")
        else:
            for key, value in entries.items():
                if key not in previous or previous[key] != value:
                    verb = "Insert" if key not in previous else "Update"
                    out.add(
                        "hashmap_insert",
                        text=name,
                        label=f"{key} → {value}",
                        values=[[key, value]],
                        caption=f"{verb} {name}[{key}] = {value}",
                    )
        previous = entries


# ---------------------------------------------------------------- graph view


def _build_graph(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    adjacency: dict[Any, list] = view.extra["adjacency"]
    nodes = list(adjacency.keys())
    edges, directed = _graph_edges(adjacency)
    names = ctx.all_names(view.ref)
    current_vars, neighbor_vars, traversal_lines = _graph_variables(ctx, names)
    # Only frames of functions that traverse the graph count: an addEdge(u, v)
    # helper has variables with the same names but is building, not visiting.
    traversing = {s["func"] for s in ctx.steps if s["line"] in traversal_lines}
    weights = {(u, v): w for u, nbrs in adjacency.items() for v, w in nbrs}
    node_keys = {str(n) for n in nodes}

    out.add(
        "show_graph",
        nodes=[str(n) for n in nodes],
        edges=[{"from": str(u), "to": str(v), **({"weight": w} if w is not None else {})} for u, v, w in edges],
        directed=directed,
        caption=f"{sorted(names)[0] if names else 'graph'}: {len(nodes)} nodes, {len(edges)} edges",
    )

    current: Any = None
    seen_current: dict[int, Any] = {}
    seen_neighbor: dict[int, Any] = {}
    previous_tables: dict[str, dict] = {}

    for index, step in enumerate(ctx.steps):
        if index < view.extra["built_at"]:
            continue
        depth = len(step["stack"])
        if step["event"] == "call":
            for d in [d for d in seen_current if d >= depth]:
                seen_current.pop(d, None)
                seen_neighbor.pop(d, None)
        frame_locals = step["stack"][-1]["locals"] if step["stack"] else {}
        if step["func"] not in traversing:
            _emit_node_tables(ctx, step, view.ref, nodes, previous_tables, out)
            continue

        for var in current_vars:
            value = _scalar(frame_locals.get(var), step["heap"])
            if str(value) in node_keys and seen_current.get(depth) != value:
                seen_current[depth] = value
                seen_neighbor.pop(depth, None)
                current = value
                out.add("visit_node", node=str(value), caption=f"Visit {value}")

        for var in neighbor_vars:
            value = _scalar(frame_locals.get(var), step["heap"])
            if current is None or value is None or seen_neighbor.get(depth) == value:
                continue
            if any(n == value for n, _w in adjacency.get(current, [])):
                seen_neighbor[depth] = value
                weight = weights.get((current, value))
                label = f" (weight {weight})" if weight is not None else ""
                out.add(
                    "relax_edge",
                    **{"from": str(current), "to": str(value)},
                    weight=weight,
                    caption=f"Look at edge {current} → {value}{label}",
                )

        _emit_node_tables(ctx, step, view.ref, nodes, previous_tables, out)


def _graph_edges(adjacency: dict[Any, list]) -> tuple[list[tuple], bool]:
    pairs = {(u, v) for u, nbrs in adjacency.items() for v, _w in nbrs}
    directed = any((v, u) not in pairs for u, v in pairs)
    edges: list[tuple] = []
    seen: set = set()
    for u, nbrs in adjacency.items():
        for v, w in nbrs:
            key = (u, v) if directed else frozenset((u, v))
            if key in seen:
                continue
            seen.add(key)
            edges.append((u, v, w))
    return edges, directed


_TYPE_WORDS = {
    "auto", "const", "let", "var", "final", "int", "long", "Integer", "String", "char",
    "double", "float", "bool", "boolean", "pair", "std", "for", "each", "unsigned", "size_t",
}


_BUILDING_CALL = re.compile(r"\s*\.\s*(add|append|push_back|push|offer|emplace_back|put|insert)\s*\(")


def _graph_variables(
    ctx: TraceContext, graph_names: set[str]
) -> tuple[list[str], list[str], set[int]]:
    """Variables used as 'current node' (graph[v]) and loop 'neighbor'
    (for x in graph[v]), plus the lines where the graph is traversed."""
    current: list[str] = []
    neighbors: list[str] = []
    traversal_lines: set[int] = set()
    for number, line in enumerate(ctx.lines, start=1):
        for name in graph_names:
            for match in re.finditer(
                rf"(?<![\w.]){re.escape(name)}\s*(?:\[\s*(\w+)\s*\]|\.get\(\s*(\w+)\s*\))", line
            ):
                if _BUILDING_CALL.match(line, match.end()):
                    continue  # adj[u].append(v) builds the graph; it is not a visit
                var = match.group(1) or match.group(2)
                if var and not var.isdigit():
                    traversal_lines.add(number)
                    if var not in current:
                        current.append(var)
                header = re.search(r"\bfor\b\s*\(?(.*?)(?:\bin\b|\bof\b|:)\s*" + re.escape(name), line)
                if header:
                    words = [w for w in re.findall(r"[A-Za-z_]\w*", header.group(1)) if w not in _TYPE_WORDS]
                    if words and words[0] not in neighbors:
                        neighbors.append(words[0])
    return current, [n for n in neighbors if n not in current], traversal_lines


def _emit_node_tables(
    ctx: TraceContext,
    step: Step,
    graph_ref: str,
    nodes: list,
    previous: dict[str, dict],
    out: SceneBuilder,
) -> None:
    """Per-node numeric tables (dist[], cost map) changing during the run."""
    node_set = set(nodes)
    for frame in step["stack"]:
        for name, value in frame["locals"].items():
            ref = _ref(value)
            if not ref or ref == graph_ref:
                continue
            table = _node_table(step["heap"].get(ref, {}), node_set)
            if table is None:
                continue
            before = previous.get(ref)
            previous[ref] = table
            if before is None:
                continue
            for node, val in table.items():
                if before.get(node) != val:
                    out.add(
                        "update_distance",
                        node=str(node),
                        label=str(val),
                        distances={str(k): v for k, v in table.items()},
                        caption=f"{name}[{node}] = {val}",
                    )


def _node_table(obj: dict[str, Any], nodes: set) -> dict | None:
    if obj.get("kind") == "list":
        items = obj.get("items") or []
        if len(items) != len(nodes) or set(range(len(items))) != nodes:
            return None
        pairs = list(enumerate(items))
    elif obj.get("kind") == "dict":
        pairs = [(k, v) for k, v in obj.get("entries") or []]
        if not pairs or not {k for k, _ in pairs} <= nodes:
            return None
    else:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) or v in ("∞", "-∞") for _, v in pairs):
        return None
    return {k: _display(v) for k, v in pairs}


# ----------------------------------------------------------------- tree view


def _build_tree(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    left, right = view.extra["self_fields"][:2]
    value_field = view.extra["value_field"]
    cls = view.extra["class"]

    best_index, best_tree, best_refs = None, None, set()
    for index, step in enumerate(ctx.steps):
        heap = step["heap"]
        roots = _tree_roots(heap, cls, left, right)
        for root in roots:
            refs: set[str] = set()
            tree = _to_tree(root, heap, left, right, value_field, refs)
            if len(refs) > len(best_refs):
                best_index, best_tree, best_refs = index, tree, refs
    if best_tree is None:
        return

    out.add("show_tree", tree=best_tree, caption=f"{cls} tree with {len(best_refs)} nodes")
    values = {ref: _node_value(ref, ctx.steps[best_index]["heap"], value_field) for ref in best_refs}
    tree_values = {str(v) for v in values.values()}

    seen: dict[tuple[int, str], str] = {}
    printed = ""
    output_lengths: dict[str, int] = {}
    for index, step in enumerate(ctx.steps):
        if index < best_index:
            printed += step.get("stdout", "")
            continue
        depth = len(step["stack"])
        if step["event"] == "call":
            for key in [k for k in seen if k[0] >= depth]:
                seen.pop(key)
        frame = step["stack"][-1] if step["stack"] else {"func": "", "locals": {}}
        for name, value in frame["locals"].items():
            ref = _ref(value)
            if ref in values and seen.get((depth, name)) != ref:
                seen[(depth, name)] = ref
                out.add(
                    "highlight_node",
                    node=values[ref],
                    caption=f"{frame['func']}({name} = {values[ref]})",
                )

        for token in re.findall(r"-?\w+", step.get("stdout", "")):
            if token in tree_values:
                out.add("visit_node", node=token, caption=f"Output {token}")

        for frame_ in step["stack"]:
            for name, value in frame_["locals"].items():
                items = _items(step["heap"].get(_ref(value) or "", {}))
                ref = _ref(value)
                if not ref or ref in values or not _all_scalars(items):
                    continue
                before = output_lengths.get(ref)
                output_lengths[ref] = len(items)
                if before is not None and len(items) == before + 1 and str(items[-1]) in tree_values:
                    out.add("visit_node", node=str(items[-1]), caption=f"Append {items[-1]} to {name}")


def _tree_roots(heap: dict[str, Any], cls: str, left: str, right: str) -> list[str]:
    nodes = [r for r, o in heap.items() if o.get("kind") == "object" and o.get("class") == cls]
    children = {
        _ref(heap[r]["fields"].get(f))
        for r in nodes
        for f in (left, right)
    }
    return [r for r in nodes if r not in children]


def _to_tree(ref: str, heap, left, right, value_field, seen: set[str]) -> dict[str, Any] | None:
    if not ref or ref in seen or ref not in heap:
        return None
    seen.add(ref)
    fields = heap[ref].get("fields") or {}
    node: dict[str, Any] = {"value": fields.get(value_field)}
    for side in (left, right):
        child = _to_tree(_ref(fields.get(side)), heap, left, right, value_field, seen)
        if child:
            node["left" if side == left else "right"] = child
    return node


def _node_value(ref: str, heap: dict[str, Any], value_field: str | None) -> Any:
    return (heap.get(ref, {}).get("fields") or {}).get(value_field, ref)


# ---------------------------------------------------------- linked list view


def _build_linked_list(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    next_field = view.extra["self_fields"][0]
    value_field = view.extra["value_field"]
    cls = view.extra["class"]

    order: list[str] = []
    for step in ctx.steps:
        heap = step["heap"]
        for root in _tree_roots(heap, cls, next_field, next_field):
            chain = []
            ref = root
            while ref and ref in heap and ref not in chain:
                chain.append(ref)
                ref = _ref((heap[ref].get("fields") or {}).get(next_field))
            if len(chain) > len(order):
                order = chain
    if len(order) < 2:
        return

    position = {ref: i for i, ref in enumerate(order)}
    last_state = None
    for index, step in enumerate(ctx.steps):
        heap = step["heap"]
        if not all(ref in heap for ref in order) or _is_constructor(step["func"]):
            continue
        links = []
        for ref in order:
            target = _ref((heap[ref].get("fields") or {}).get(next_field))
            if target in position:
                links.append({"from": position[ref], "to": position[target]})
        frame = step["stack"][-1] if step["stack"] else {"locals": {}}
        pointers = {
            name: position.get(_ref(value)) if _ref(value) else None
            for name, value in frame["locals"].items()
            if _ref(value) in position or (value is None and name not in {"next"})
        }
        state = (tuple((l["from"], l["to"]) for l in links), tuple(sorted(pointers.items(), key=str)))
        if state == last_state:
            continue
        last_state = state
        values = [_display(_node_value(ref, heap, value_field)) for ref in order]
        out.add(
            "show_linked_list",
            nodes=values,
            edges=links,
            variables=pointers,
            caption=_after_line(ctx, index),
        )


# ----------------------------------------------------------- call stack view


def _build_call_stack(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    open_calls: list[str] = []
    for step in ctx.steps:
        func = step["func"]
        if _is_constructor(func) or func == "<module>" or (func == "main" and ctx.language in {"java", "cpp"}):
            continue
        if step["event"] == "call":
            args = ", ".join(
                f"{k}={_display(_scalar(v, step['heap']) if _ref(v) is None else _short_obj(v, step['heap']))}"
                for k, v in step["stack"][-1]["locals"].items()
            )
            label = f"{func}({args})"
            open_calls.append(label)
            out.add("push_stack", label=label, caption=f"Call {label}")
        elif step["event"] == "return" and open_calls:
            label = open_calls.pop()
            result = step.get("return_value")
            value = _display(_scalar(result, step["heap"])) if _ref(result) is None else _short_obj(result, step["heap"])
            out.add("pop_stack", label=label, caption=f"{label} returns {value}")


# ------------------------------------------------------------ variables view


def _build_variables(ctx: TraceContext, view: View, out: SceneBuilder) -> None:
    previous: dict[str, Any] | None = None
    for step in ctx.steps:
        frame = step["stack"][-1] if step["stack"] else {"locals": {}}
        scalars = {
            k: _display(v) for k, v in frame["locals"].items() if isinstance(v, SCALAR_TYPES)
        }
        if scalars and scalars != previous:
            out.add("show_variables", variables=scalars, caption=_after_line(ctx, ctx.steps.index(step)))
            previous = scalars


VIEW_BUILDERS = {
    "array": _build_array,
    "grid": _build_grid,
    "stack": _build_stack,
    "hashmap": _build_hashmap,
    "graph": _build_graph,
    "tree": _build_tree,
    "linked_list": _build_linked_list,
    "call_stack": _build_call_stack,
    "variables": _build_variables,
}


# ------------------------------------------------------------------- helpers


def _title(ctx: TraceContext, view: View) -> str:
    funcs = ctx.user_functions()
    main_steps = sum(1 for st in ctx.steps if st["func"] == "main")
    if funcs and funcs.most_common(1)[0][1] >= main_steps:
        return f"{funcs.most_common(1)[0][0]}() step by step"
    return "Your code step by step"


def _entry_result(ctx: TraceContext) -> str | None:
    """'f(...) returns X' for the outermost user call (what the code computed)."""
    ignored = lambda f: f in {"<module>", "<static>"} or _is_constructor(f) or _is_anonymous(f) or (
        f == "main" and ctx.language in {"java", "cpp"}
    )
    top = None
    for step in ctx.steps:
        if step["event"] != "return" or ignored(step["func"]):
            continue
        depth = sum(1 for frame in step["stack"] if not ignored(frame["func"]))
        if top is None or depth <= top[0]:
            top = (depth, step)
    if top is None:
        return None
    step = top[1]
    value = step.get("return_value")
    if value is None:
        return None
    shown = _short_obj(value, step["heap"]) if _ref(value) else _display(value)
    return f"{step['func']}() returns {shown}"


def _after_line(ctx: TraceContext, index: int) -> str:
    """Caption for the state at steps[index]: the code that just produced it."""
    previous = index - 1
    while previous >= 0 and _is_constructor(ctx.steps[previous]["func"]):
        previous -= 1  # constructor internals are setup, not the story
    if previous < 0:
        return "Start"
    line = ctx.steps[previous]["line"]
    code = _strip_comment(ctx.source(line)).strip()
    return f"After line {line}: {code[:56]}" if code else f"After line {line}"


def _ref(value: Any) -> str | None:
    return value.get("ref") if isinstance(value, dict) else None


def _is_constructor(name: str) -> bool:
    """Object setup frames across languages (Python __init__, JS constructor, Java <init>)."""
    return (name.startswith("__") and name.endswith("__")) or name in {"constructor", "<init>", "<clinit>"}


def _is_anonymous(name: str) -> bool:
    return name.startswith("<") and name != "<module>"


def _items(obj: dict[str, Any]) -> list:
    return list(obj.get("items") or []) if obj.get("kind") in {"list", "tuple"} else []


def _all_scalars(items: list) -> bool:
    return all(isinstance(v, SCALAR_TYPES) for v in items)


def _is_scalar_list(snaps: list[tuple[int, dict]]) -> bool:
    return all(
        obj.get("kind") in {"list", "tuple"} and _all_scalars(obj.get("items") or [])
        for _i, obj in snaps
    ) and any(obj.get("items") for _i, obj in snaps)


def _mutation_count(snaps: list[tuple[int, dict]]) -> int:
    changes = 0
    for (_a, before), (_b, after) in zip(snaps, snaps[1:]):
        if before != after:
            changes += 1
    return changes


def _items_at(step: Step, ref: str) -> list | None:
    obj = step["heap"].get(ref)
    if obj is None or obj.get("kind") not in {"list", "tuple"}:
        return None
    return list(obj.get("items") or [])


def _entries_at(step: Step, ref: str) -> dict | None:
    obj = step["heap"].get(ref)
    if obj is None or obj.get("kind") != "dict":
        return None
    return {
        _display(_scalar(k, step["heap"])): _display(_scalar(v, step["heap"]) if _ref(v) is None else _short_obj(v, step["heap"]))
        for k, v in obj.get("entries") or []
    }


def _frame_holding(step: Step, ref: str) -> dict[str, Any] | None:
    for frame in reversed(step["stack"]):
        if any(_ref(v) == ref for v in frame["locals"].values()):
            return frame
    return None


def _aliases(step: Step, ref: str) -> set[str]:
    return {
        name
        for frame in step["stack"]
        for name, value in frame["locals"].items()
        if _ref(value) == ref
    }


def _scalar_env(step: Step) -> dict[str, Any]:
    env: dict[str, Any] = {}
    for frame in step["stack"]:  # inner frames override outer names
        for name, value in frame["locals"].items():
            if isinstance(value, SCALAR_TYPES):
                env[name] = value
            else:
                env.pop(name, None)
    return env


def _scalar(value: Any, heap: dict[str, Any]) -> Any:
    return value if isinstance(value, SCALAR_TYPES) else None


def _short_obj(value: Any, heap: dict[str, Any]) -> str:
    obj = heap.get(_ref(value) or "", {})
    if obj.get("kind") in {"list", "tuple", "set"}:
        return _fmt_list([_display(v) if isinstance(v, SCALAR_TYPES) else "…" for v in obj.get("items") or []])
    if obj.get("kind") == "object":
        return obj.get("class", "object")
    if obj.get("kind") == "dict":
        return "{…}"
    return "…"


def _display(value: Any) -> Any:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int) and abs(value) >= INFINITY_THRESHOLD:
        return "∞" if value > 0 else "-∞"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if value is None:
        return "null"
    return value


def _fmt_list(values: list) -> str:
    text = "[" + ", ".join(str(v) for v in values) + "]"
    return text if len(text) <= 48 else text[:45] + "…]"


def _strip_comment(line: str) -> str:
    return re.split(r"\s#|//", line, maxsplit=1)[0]
