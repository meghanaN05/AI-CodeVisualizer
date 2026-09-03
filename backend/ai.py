"""Generate animation plans using an LLM 'thinker' or rule-based fallback.

The LLM is treated as a PLANNER, never a Manim author. Given the real source
code, it decides WHICH approach/applies (what structure, what algorithm) and
emits a structured, validated DSL describing WHAT to show and in what order.
The deterministic renderer later decides WHERE to place objects and HOW to
animate them.
"""

from __future__ import annotations

import json
import os
from typing import Any

from animation_planner import plan_from_ir
from animation_schema import AnimationPlan, validate_animation_plan

LLM_PROMPT = """You are the PLANNING stage of a code-visualization compiler.

You receive the user's real source code PLUS a shallow parse (IR).
Your job is to:
  1. Decide WHICH approach applies — the data structure(s) and algorithm(s)
     at work (e.g. weighted graph + Dijkstra, binary tree + inorder, array +
     bubble sort, hash map + heap, recursion, system design).
  2. Extract the ACTUAL data the code operates on from the source code —
     the real graph edges and weights, array values, tree, etc. If the data
     is passed in as a parameter and never appears literally in the code, use
     nil for that field rather than inventing numbers.
  3. Emit ONLY the structured plan below (valid JSON, no markdown).

The plan schema is:
{
  "approach": {
    "data_structure": "graph | binary_tree | array | stack | queue | heap | hash_map | composite",
    "algorithm": "dijkstra | bfs | dfs | inorder_traversal | binary_search | bubble_sort | ...",
    "kind": "graph_problem | tree_problem | array_problem | design | recursion"
  },
  "title": "string",
  "description": "string",
  "graph": {
     "type": "graph",
     "nodes": [{"id": "A", "label": "A"}],
     "edges": [{"from": "A", "to": "B", "weight": 4}],
     "layout": {"A": [-3, 1], "B": [3, 1]}
  },
  "scenes": [ ... scene actions ... ]
}

Supported scene actions (ONLY these):
  {"action": "show_title", "text": "..."}
  {"action": "show_graph", "nodes": ["A", "B"], "edges": [{"from": "A", "to": "B", "weight": 4}], "directed": false, "layout": {"A": [-3, 1], "B": [3, 1]}, "caption": "..."}
  {"action": "show_weighted_graph", "graph": {...}, "caption": "..."}
  {"action": "visit_node", "node": "A", "caption": "..."}
  {"action": "relax_edge", "from": "A", "to": "B", "weight": 4, "caption": "..."}
  {"action": "update_distance", "node": "B", "distances": {"A":0,"B":4}, "label":"4", "caption": "..."}
  {"action": "show_shortest_path", "path": ["A","B"], "graph": {...}, "caption": "..."}
  {"action": "create_array", "values": [5, 2, 8], "caption": "..."}
  {"action": "highlight_index", "index": 0, "label": "i", "caption": "..."}
  {"action": "show_tree", "tree": {"value": 10, "left": {...}}, "caption": "..."}
  {"action": "highlight_node", "node": 10, "caption": "..."}
  {"action": "push_stack", "label": "fact(4)", "caption": "..."}
  {"action": "pop_stack", "label": "fact(4)", "caption": "..."}
  {"action": "show_variables", "variables": {"low":0,"high":7}, "caption": "..."}
  {"action": "show_caption", "text": "..."}

Rules:
- Derive nodes/edges/weights/values from the REAL code. When data is absent
  (only a parameter), set graph to null instead of fabricating values.
- For all new graph scenes, emit "show_graph" with nodes, edges, directed,
  and optional edge weights. Use "show_weighted_graph" only for legacy
  compatibility if you must preserve an existing scene shape.
- Provide a step-by-step scene list that actually shows the algorithm running
  on the extracted data (settle nodes, relax edges, update distances, etc.).
- Return ONLY valid JSON.

SOURCE CODE:
{source_code}

PARSED IR (shallow, may be partial):
{ir_json}
"""


def generate_animation_plan(ir: dict[str, Any]) -> dict[str, Any]:
    llm_plan = _try_llm_plan(ir)
    if llm_plan is not None:
        return llm_plan

    plan = plan_from_ir(ir)
    return plan.to_dict()


def _try_llm_plan(ir: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=api_key)
    prompt = LLM_PROMPT.format(
        source_code=ir.get("source_code", ""),
        ir_json=json.dumps(ir, indent=2),
    )

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": "You are the planning stage of a code-to-visualization compiler. You output only valid JSON animation plans.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        resolve = _resolve_plan(data, ir)
        if resolve is None:
            return None
        plan = validate_animation_plan(resolve)
        return plan.to_dict()
    except Exception:
        return None


def _resolve_plan(data: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize the LLM's planned idea into the AnimationPlan shape.

    Carries the LLM's chosen graph (and its nodes/edges) through to the
    AnimationPlan top-level keys so the rule-based scene builder can act on
    the same real data, and so the renderer receives node coordinates.
    """
    approach = data.get("approach") or {}
    graph = data.get("graph")
    scenes = data.get("scenes")

    resolved: dict[str, Any] = {
        "algorithm": approach.get("algorithm") or data.get("algorithm"),
        "title": data.get("title", "Code Visualization"),
        "data_structure": approach.get("data_structure") or data.get("data_structure"),
        "kind": approach.get("kind") or data.get("kind"),
        "description": data.get("description"),
        "scenes": scenes or [],
    }

    if isinstance(graph, dict):
        resolved["graph"] = graph

    # Canonicalize new graph output onto show_graph so weighted and
    # unweighted graphs share the same planner/scene contract.
    if graph and not any(
        s.get("action") in {"show_graph", "show_weighted_graph"}
        for s in resolved["scenes"]
    ):
        resolved["scenes"].insert(
            0,
            {
                "action": "show_graph",
                "nodes": graph.get("nodes", []),
                "edges": graph.get("edges", []),
                "directed": graph.get("directed", False),
                "layout": graph.get("layout", {}),
                "caption": "Graph from your code",
            },
        )

    return resolved
