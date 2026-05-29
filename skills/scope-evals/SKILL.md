---
name: scope-evals
description: Configure manual-trigger judges in Opik — derive one evaluator dimension per promise, **match against existing evaluators on the account first**, generate `_local/create_evaluators.py` only for gaps, run it. Output is `.edd/evaluator-plan.md` + judges live in Opik with `enabled=False, sampling_rate=1.0` (disabled blocks auto-firing during experimentation; sampling_rate pre-staged so flipping to auto-sample is a one-field change). Invoke as `edd:scope-evals` or when the user says "set up judges", "create evaluators", "scope the evals". For *firing* judges and reading scores, see `edd:run`.
---

# edd:scope-evals — evaluator dimensions + Opik judges

Discovery step 2 of the eval pipeline. Reads the promise inventory, decides which judges are needed, reuses what exists, creates gaps.

## Preconditions

- `.edd/promises.md` exists (run [`edd:scope-agent`](../scope-agent/SKILL.md) first)
- Opik creds in `.env`: `OPIK_URL`, `OPIK_API_KEY`
- Opik project named in `.edd/session.json` (or ask the user — must be a dedicated **testing** project, not production)

## Step 1 — Derive dimensions from promises

For each line in `.edd/promises.md`, map to one evaluator dimension. Follow [references/evaluator-selection.md](../../references/evaluator-selection.md). Categories:

- **Trigger correctness** — did the agent fire the right skill/tool?
- **Output fidelity** — does the response match the promised shape?
- **Boundary respect** — does it refuse / escalate when the promise requires?
- **Tool usage** — were the right tools called in the right order?

Write derived dimensions to `.edd/evaluator-plan.md`:

```
- <Dimension Name> → covers promise: <surface>
  Variable paths: metadata.user_message, metadata.assistant_response, metadata.tools_called
  Scoring: 1 = explicitly verified, 0 = failed OR not applicable
```

## Step 2 — Reuse-first match against existing Opik evaluators

Skipping this step burns tokens creating duplicates. Reuse beats create.

Pull existing evaluators (names + prompts) from the project:

```python
import sys; sys.path.insert(0, 'scripts')
from shared.opik_client import OpikClient
evs = OpikClient().get_evaluators().get("content", [])
project_evs = [e for e in evs if e.get("project_name") == "<opik-project>"]
for e in project_evs:
    print(OpikClient.evaluator_schema_name(e))
    print("  prompt:", ((e.get("code") or {}).get("prompt") or "")[:300])
```

For each derived dimension, **read both the existing eval's name and its prompt** — name similarity alone is misleading (`grounding` vs `ticket-grounding` may or may not score the same thing). Match when:

- the existing rubric scores the same promise (compare against the dimension's success/failure criteria), and
- its variable paths align with what enrichment populates (`metadata.*`).

Mark the dimension in `.edd/evaluator-plan.md`:

- **REUSE: `<existing-schema-name>`** — record the existing schema name verbatim. `edd:run` / `edd:experiment` `--evaluator` flag uses it as-is.
- **CREATE** — no good match; gap goes to Step 3.

When unsure between REUSE and CREATE, default to REUSE if the existing rubric is within shouting distance of the promise. Recalibrating one judge is cheaper than maintaining two near-duplicates.

## Step 3 — Build missing evaluators

**Deterministic dimension?** → code metric, not an LLM judge. Write a `BaseMetric` subclass in `scripts/metrics/`, add it to `ALL_METRICS`, register with `edd-metrics --project <name>`. See [`scripts/metrics/CLAUDE.md`](../../scripts/metrics/CLAUDE.md). Skip the template below for these.

**Subjective dimension?** → LLM judge via the template below.

### Generate `_local/create_evaluators.py` (LLM judges only)

One block per **CREATE** subjective dimension. Template:

```python
from shared.opik_client import OpikClient
c = OpikClient()

c.create_evaluator(
    project_name="<opik-project>",
    name="<Dimension Name>",
    prompt="""You are scoring whether <promise>.

Score 1 if: <explicit success criteria, observable in the trace>
Score 0 if: <failure OR not applicable — anything we can't verify>

Trace input: {{metadata.user_message}}
Trace output: {{metadata.assistant_response}}
Tools called: {{metadata.tools_called}}

Return JSON: {"score": 0|1, "reason": "<one sentence>"}""",
    model="anthropic/claude-sonnet-4-6",
    enabled=False,         # disabled blocks automatic firing during experimentation — skill decides when to fire
    sampling_rate=1.0,     # pre-stage full sampling so flipping `enabled=True` later is a one-field change
)
```

Rules baked into the template:
- **`enabled=False` is the gate.** `trigger_evaluation` ignores both flags and manual-fires anyway, so the skill always controls when judges run during the inner loop / experiment. Disabled prevents *automatic* firing on stray traces (concurrent dev, prod traffic in shared projects).
- **`sampling_rate=1.0` is staging.** When you graduate the judge to auto-sample mode (rubric calibrated, watching prod), flipping `enabled=True` is the only change needed. Avoids "I enabled it but nothing fires" foot-gun from `sampling_rate=0`.
- **Read from `metadata.*`.** Enrichment populates these (see `_local/enrich_traces_<sdk>.py`); never wire the judge to native SDK trace paths.
- **Binary scoring.** 1 = explicitly verified correct, 0 = failed OR not applicable. No half-credit, no NA.

## Step 4 — Run it

```bash
python _local/create_evaluators.py
```

Re-listing via `c.get_evaluators()` should now show every dimension from the plan.

## Step 5 — Document variable paths

Append to `.edd/evaluator-plan.md` which trace paths each judge expects. This is what `_local/enrich_traces_<sdk>.py` must populate — `edd:run` reads this file to know whether enrichment is needed.

## Step 6 — Cache evaluator state to `.edd/evaluators.json`

After Step 4 lands, dump the current set of judge names into a local cache file so the `edd:edd` router (and downstream skills) can answer "do all required evaluators exist?" without a live Opik call. Avoids the foot-gun where Phase A can't self-verify because the Opik MCP server has no `list-evaluators` endpoint.

```python
import json, sys
sys.path.insert(0, 'scripts')
from pathlib import Path
from shared.opik_client import OpikClient

names = OpikClient().list_evaluator_names()  # for the project in .env
Path(".edd").mkdir(exist_ok=True)
Path(".edd/evaluators.json").write_text(json.dumps({"names": names}, indent=2))
```

Refresh this file whenever judges are created/renamed/deleted. The router treats it as advisory: if the file is missing or stale, it falls back to a live `list_evaluator_names()` call.

## Outputs

| File | Purpose |
|---|---|
| `.edd/evaluator-plan.md` | Dimension → promise mapping, REUSE/CREATE marks, variable paths |
| `.edd/evaluators.json` | Cached set of evaluator names — read by `edd:edd` router for Phase A |
| `_local/create_evaluators.py` | Idempotent script that creates missing judges in Opik |
| Opik project | Judges live here, manual-trigger mode |

## Anti-patterns

- Creating one mega-judge that scores "overall quality" — score per dimension or you lose signal.
- Leaving `enabled=True` at creation — judges will fire on every matching trace (sim + prod + stray dev) and burn LLM spend before the rubric is calibrated.
- Re-creating judges that already exist — Step 2 reuse-match is the gate. Match by *rubric*, not just by name.
- Reading from native SDK trace paths in the judge prompt — write from `metadata.*` only.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global).

## Next

→ [`edd:run`](../run/SKILL.md) — fire scenarios, tag traces, score with these judges.
