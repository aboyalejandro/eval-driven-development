# scripts/metrics/ — deterministic code-based metrics

Opik `user_defined_metric_python` automation rules. Each metric is a self-contained `BaseMetric` subclass that scores traces deterministically — no LLM call, no API key, runs server-side in Opik.

## When to use

Pick a code metric over an LLM judge when the dimension is **structural**: a tool was called (or not), the output matches a pattern, an internal tag didn't leak. Reach for an LLM judge only when the dimension requires genuine interpretation. See [`../../references/eval-fundamentals.md`](../../references/eval-fundamentals.md) and [`../../references/evaluator-selection.md`](../../references/evaluator-selection.md) Step 3.

## Layout

| File | Role |
|---|---|
| `tool_call_presence.py` | At least one tool call present; optional `required_tool` name check |
| `format_compliance.py` | Output matches a regex pattern and/or is valid JSON |
| `system_prompt_leakage.py` | Internal XML markers don't appear in agent output |
| `registry.py` | `ALL_METRICS` list + `build_payload(cls, project_id)` — builds the POST body |
| `register.py` | CLI: idempotent POST/PATCH metrics to an Opik project |
| `tests/test_metrics.py` | Offline pytest — no Opik creds needed |

## BaseMetric contract

```python
from opik.evaluation.metrics import base_metric, score_result

class MyMetric(base_metric.BaseMetric):
    def __init__(self, name: str = "my_metric"):
        self.name = name          # short snake_case — lands in feedback_scores + score table

    def score(self, input, output, metadata=None, **kwargs) -> score_result.ScoreResult:
        ...
        return score_result.ScoreResult(name=self.name, value=0|1, reason="one sentence")
```

**Must be self-contained.** All imports inside the file — Opik executes the source server-side.

**`name` is the primary key.** It's what `edd score -e <name>` and the score-table column headers use. Keep it stable; renames require delete + re-register.

**Binary scoring.** `value=1` = verified correct. `value=0` = failed OR not applicable (same convention as LLM judges — see `score-reading.md`).

**`OPIK_ARGUMENTS` override.** Override the default JSONPath mapping per class if your trace shape differs:
```python
class MyMetric(base_metric.BaseMetric):
    OPIK_ARGUMENTS = {"input": "input.message", "output": "output.text", "metadata": "metadata"}
```

Default mapping (OpenInference/Agno traces): `input.input.value`, `output.output.value`, `metadata`.

## Register flow

```bash
cd scripts && source .venv/bin/activate

# 1. Dry-run — inspect payloads without POSTing
edd-metrics --project <name> --dry-run

# 2. Register (disabled — safe to run anytime)
edd-metrics --project <name>

# 3. Fire on recent traces and check scores
edd score -e tool_call_presence --since 30

# 4. When rubric validated, enable for auto-sampling
edd-metrics --project <name> --enable
```

**Always dry-run first.** `--dry-run` prints the full payload (minus the `code` blob) so you can verify name + arguments before touching Opik.

**PATCH caveat.** Opik's PATCH endpoint does **not** replace the `code` field. To update metric logic: `edd-metrics` does PATCH for all fields except code; to replace source use `OpikClient.delete_evaluators_by_name` then re-run `edd-metrics`.

## Adding a new metric

1. Write `scripts/metrics/<your_metric>.py` — single self-contained `BaseMetric` subclass.
2. Import and add the class to `ALL_METRICS` in `registry.py`.
3. Add tests in `tests/test_metrics.py` — at minimum: pass, fail, None-output cases.
4. Run `pytest metrics/tests` green.
5. Register with `edd-metrics --project <name> --dry-run` to verify the payload shape.

## Tests

```bash
cd scripts && source .venv/bin/activate
pytest metrics/tests -v
```

Tests are pure-function (no Opik creds needed). Each metric gets: a pass case, a fail case, a None-output case, and any option-specific cases.

## Up one level

- Engine: [../CLAUDE.md](../CLAUDE.md)
- Evaluator selection: [../../references/evaluator-selection.md](../../references/evaluator-selection.md)
