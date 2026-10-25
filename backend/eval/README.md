# Visualization accuracy eval

Golden snippets (`snippets/`) paired with what a faithful video of each must
contain (`cases.json`). `run_eval.py` runs the planner on every snippet and
scores the scene plan; it does not render video unless `--render` is passed.

```bash
cd backend
.venv/bin/python eval/run_eval.py              # deterministic baseline, LLM disabled
.venv/bin/python eval/run_eval.py --llm        # include the OpenAI planner
.venv/bin/python eval/run_eval.py --case py_two_sum -v
.venv/bin/python eval/run_eval.py --render     # also produce MP4s for eyeballing
```

Checks per case (score = mean of the applicable checks):

| check | passes when |
|---|---|
| `visual` | the right view appears (array, graph, tree, call stack, hash map, ...) |
| `events` | the expected step actions appear (compare, swap, visit, push/pop, ...) |
| `data` | the snippet's real values appear in that view's data fields |
| `final_array` | the last array state equals what the code really produces |
| `no_placeholder` | no built-in demo dataset was substituted for the user's data |

Adding a case: drop a snippet under `snippets/<language>/`, add an entry to
`cases.json`, and keep expectations about *what the code does*, not about the
current implementation's scene names where avoidable. When the DSL gains a new
view action, map it in `VISUAL_ACTIONS` in `run_eval.py`.
