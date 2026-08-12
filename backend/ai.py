"""Generate animation plans from IR using LLM or rule-based fallback."""

from __future__ import annotations

import json
import os
from typing import Any

from animation_planner import plan_from_ir
from animation_schema import AnimationPlan, validate_animation_plan

LLM_PROMPT = """You are an algorithm visualization planner.
Given a program intermediate representation (IR), produce a JSON animation plan.

The plan must follow this schema:
{
  "algorithm": "string",
  "title": "string",
  "data_structure": "array | binary_tree | graph | stack | queue",
  "description": "string",
  "scenes": [
    {"action": "show_title", "text": "..."},
    {"action": "create_array", "values": [5, 2, 8]},
    {"action": "highlight_index", "index": 0, "label": "i = 0", "caption": "..."},
    {"action": "show_tree", "tree": {"value": 10, "left": {"value": 5}, "right": {"value": 20}}},
    {"action": "highlight_node", "node": 10, "caption": "..."},
    {"action": "move_pointer", "from": 10, "to": 5, "caption": "..."},
    {"action": "visit_node", "node": 10, "caption": "..."},
    {"action": "show_variables", "variables": {"low": 0, "high": 7, "mid": 3}},
    {"action": "compare_indices", "index": 0, "label": "1"},
    {"action": "swap_indices", "index": 0, "label": "1", "values": [2, 5, 8]},
    {"action": "show_class_methods", "text": "Twitter", "nodes": ["postTweet", "getNewsFeed"]},
    {"action": "show_hashmap", "text": "tweets", "values": [["user 1", "tweet list"]]},
    {"action": "hashmap_insert", "text": "tweets", "label": "user 1 → (t, id)"},
    {"action": "show_heap", "values": [["(t, id)", 10]]},
    {"action": "heap_push", "label": "(t, id)"},
    {"action": "heap_pop", "label": "tweetId"},
    {"action": "show_method_flow", "text": "postTweet", "caption": "..."},
    {"action": "show_graph", "nodes": ["A", "B", "C", "D"]},
    {"action": "push_stack", "label": "fact(4)"},
    {"action": "pop_stack", "label": "fact(4)"},
    {"action": "show_caption", "text": "..."}
  ]
}

Rules:
- Return ONLY valid JSON, no markdown.
- Use only supported actions listed above.
- Prefer concrete step-by-step scenes over vague descriptions.
- For arrays, use values from IR when available.
- For tree traversals, include show_tree then highlight/visit/move scenes.

IR:
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
    prompt = LLM_PROMPT.format(ir_json=json.dumps(ir, indent=2))

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": "You output only valid JSON animation plans.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        plan = validate_animation_plan(data)
        return plan.to_dict()
    except Exception:
        return None
