"""Score the visualization pipeline against golden snippets.

Each case in cases.json pairs a pasted snippet with what a faithful video of
that snippet must contain. The harness runs the planner (not Manim, unless
--render is given) and checks the resulting scene plan:

  visual        the right kind of view appears (array, graph, tree, ...)
  events        the expected step actions appear (compare, swap, visit, ...)
  data          the snippet's real values appear in the structured scene data
  final_array   the last array state matches what the code actually produces
  no_placeholder  the plan does not fall back to a built-in demo dataset

Usage (from backend/):
  .venv/bin/python eval/run_eval.py                 # deterministic, no LLM
  .venv/bin/python eval/run_eval.py --llm           # allow OPENAI_API_KEY
  .venv/bin/python eval/run_eval.py --case py_two_sum --verbose
  .venv/bin/python eval/run_eval.py --render        # also render MP4s
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent
SNIPPETS_DIR = EVAL_DIR / "snippets"
REPORTS_DIR = EVAL_DIR / "reports"

# Scene actions that count as showing each kind of view. Extend this when the
# DSL gains new actions (e.g. a dedicated linked-list view).
VISUAL_ACTIONS: dict[str, set[str]] = {
    "array": {"create_array"},
    "graph": {"show_graph", "show_weighted_graph"},
    "tree": {"show_tree"},
    "call_stack": {"push_stack"},
    "stack": {"push_stack"},
    "hashmap": {"show_hashmap", "hashmap_insert"},
    "heap": {"show_heap", "heap_push"},
    "linked_list": {"show_linked_list"},
}

ARRAY_STATE_ACTIONS = {"create_array", "swap_indices", "set_index"}

# Fields whose values are prose or geometry rather than the program's data;
# a number in a caption or a coordinate must not count as "real data shown".
NON_DATA_FIELDS = {"action", "caption", "text", "layout", "index", "directed"}

# Demo datasets the planners substitute when extraction fails. Seeing one of
# these in a plan means the video shows made-up data.
PLACEHOLDER_SIGNATURES: dict[str, set[str]] = {
    "default_graph_A_to_E": {"A", "B", "C", "D", "E"},
    "default_tree_10_5_20": {"10", "5", "3", "7", "20"},
    "default_sort_array": {"64", "34", "25", "12", "22", "11", "90"},
    "default_search_array": {"2", "5", "8", "16", "23", "38", "56", "72", "91"},
    "twitter_demo_users": {"user 1", "user 2"},
}


def main() -> int:
    args = _parse_args()
    if not args.llm:
        os.environ.pop("OPENAI_API_KEY", None)

    sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)
    from pipeline import build_visualization_plan

    cases = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] in set(args.case)]
        if not cases:
            print(f"No cases match {args.case}", file=sys.stderr)
            return 2

    results = []
    for case in cases:
        code = (SNIPPETS_DIR / case["file"]).read_text(encoding="utf-8")
        started = time.perf_counter()
        try:
            plan = build_visualization_plan(code, case["language"])
            error = None
        except Exception as exc:  # the harness must survive pipeline crashes
            plan = None
            error = f"{type(exc).__name__}: {exc}"
            if args.verbose:
                traceback.print_exc()
        elapsed = time.perf_counter() - started

        checks = score_plan(plan, case["expect"]) if plan else {}
        score = sum(checks.values()) / len(checks) if checks else 0.0
        result = {
            "id": case["id"],
            "language": case["language"],
            "score": round(score, 3),
            "checks": {k: round(v, 3) for k, v in checks.items()},
            "title": (plan or {}).get("title"),
            "algorithm": (plan or {}).get("algorithm"),
            "scene_count": len((plan or {}).get("scenes") or []),
            "seconds": round(elapsed, 2),
            "error": error,
        }
        if args.render and plan:
            result["video"] = _render(plan)
        if args.verbose and plan:
            result["actions"] = [s.get("action") for s in plan.get("scenes", [])]
        results.append(result)

    _print_report(results, verbose=args.verbose)
    report_path = _write_report(results, args)
    print(f"\nReport written to {report_path.relative_to(BACKEND_DIR)}")
    return 0


def score_plan(plan: dict[str, Any], expect: dict[str, Any]) -> dict[str, float]:
    scenes = plan.get("scenes") or []
    actions = {s.get("action") for s in scenes}
    leaves = _data_leaves(scenes)
    checks: dict[str, float] = {}

    visual = expect.get("visual")
    if visual:
        checks["visual"] = 1.0 if actions & VISUAL_ACTIONS.get(visual, set()) else 0.0

    events = expect.get("events") or []
    if events:
        checks["events"] = sum(1 for e in events if e in actions) / len(events)

    data_values = expect.get("data_values") or []
    if data_values:
        wanted = {_norm(v) for v in data_values}
        shown = _visual_leaves(scenes, visual)
        checks["data"] = len(wanted & shown) / len(wanted)

    final_array = expect.get("final_array")
    if final_array is not None:
        checks["final_array"] = 1.0 if _last_array_state(scenes) == [
            _norm(v) for v in final_array
        ] else 0.0

    expected_leaves = {_norm(v) for v in data_values} | {
        _norm(v) for v in final_array or []
    }
    checks["no_placeholder"] = 0.0 if _placeholders_used(leaves, expected_leaves) else 1.0
    return checks


def _visual_leaves(scenes: list[dict[str, Any]], visual: str | None) -> set[str]:
    """Values shown in the fields that carry this view's data.

    Scoping matters: small integers are everywhere (indices, weights,
    distances), so a graph's node ids must be found among node fields and an
    array's values among array values, or placeholder data would pass.
    """
    if visual == "graph":
        out: set[str] = set()
        for scene in scenes:
            graph = scene.get("graph") or {}
            for node in (scene.get("nodes") or []) + (graph.get("nodes") or []):
                out.add(_norm(node.get("id") if isinstance(node, dict) else node))
            for edge in (scene.get("edges") or []) + (graph.get("edges") or []):
                if isinstance(edge, dict):
                    out |= {_norm(edge.get("from")), _norm(edge.get("to"))}
        return out
    if visual == "array":
        return {
            _norm(v)
            for scene in scenes
            if scene.get("action") in ARRAY_STATE_ACTIONS
            for v in scene.get("values") or []
        }
    if visual == "tree":
        return set().union(*(_data_leaves(s.get("tree")) for s in scenes)) if scenes else set()
    return _data_leaves(scenes)


def _data_leaves(value: Any, field: str | None = None) -> set[str]:
    if field in NON_DATA_FIELDS:
        return set()
    if isinstance(value, dict):
        out: set[str] = set()
        for key, child in value.items():
            out |= _data_leaves(child, key)
        return out
    if isinstance(value, (list, tuple)):
        out = set()
        for child in value:
            out |= _data_leaves(child, field)
        return out
    if value is None or isinstance(value, bool):
        return set()
    return {_norm(value)}


def _norm(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _last_array_state(scenes: list[dict[str, Any]]) -> list[str] | None:
    for scene in reversed(scenes):
        if scene.get("action") in ARRAY_STATE_ACTIONS and scene.get("values"):
            return [_norm(v) for v in scene["values"]]
    return None


def _placeholders_used(leaves: set[str], expected: set[str]) -> list[str]:
    return [
        name
        for name, signature in PLACEHOLDER_SIGNATURES.items()
        if signature <= leaves and not signature <= expected
    ]


def _render(plan: dict[str, Any]) -> str | None:
    from manim_generator import generate_manim_code
    from renderer import render_video

    try:
        return render_video(generate_manim_code(plan))
    except Exception as exc:
        return f"render failed: {exc}"


def _print_report(results: list[dict[str, Any]], verbose: bool) -> None:
    id_width = max(len(r["id"]) for r in results)
    print(f"{'case'.ljust(id_width)}  score  failing checks / plan title")
    print("-" * (id_width + 60))
    for r in results:
        failing = [k for k, v in r["checks"].items() if v < 1.0]
        detail = r["error"] or (
            f"{', '.join(failing) or 'all pass'}  [{r['title']}]"
        )
        print(f"{r['id'].ljust(id_width)}  {r['score']:.2f}   {detail}")
        if verbose and r.get("actions"):
            print(f"{''.ljust(id_width)}         actions: {r['actions']}")
        if r.get("video"):
            print(f"{''.ljust(id_width)}         video: {r['video']}")

    by_lang: dict[str, list[float]] = defaultdict(list)
    by_check: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_lang[r["language"]].append(r["score"])
        for k, v in r["checks"].items():
            by_check[k].append(v)

    overall = sum(r["score"] for r in results) / len(results)
    print("\nBy language: " + "  ".join(
        f"{lang}={sum(s) / len(s):.2f}" for lang, s in sorted(by_lang.items())
    ))
    print("By check:    " + "  ".join(
        f"{k}={sum(v) / len(v):.2f}" for k, v in by_check.items()
    ))
    print(f"Overall:     {overall:.2f}  ({len(results)} cases)")


def _write_report(results: list[dict[str, Any]], args: argparse.Namespace) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / "latest.json"
    path.write_text(
        json.dumps(
            {
                "llm": args.llm,
                "overall": round(sum(r["score"] for r in results) / len(results), 3),
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", help="Run only this case id (repeatable)")
    parser.add_argument("--llm", action="store_true", help="Keep OPENAI_API_KEY so the LLM planner runs")
    parser.add_argument("--render", action="store_true", help="Also render each plan to MP4")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show scene actions and tracebacks")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
