---
name: run
description: Fire scenarios at the agent and read the score table. Mode 1 reads traces inline with no judges; Mode 2 Phase 1 triggers manual-fire judges that `edd:scope-evals` already created and prints the per-dimension table. Generates `scenarios.txt` at session aggression level; branches on whether trace enrichment runs between emit and score. Invoke as `edd:run` or when the user says "run scenarios", "score traces", "fire judges", "edd inner loop". For *creating* judges, see `edd:scope-evals`.
---

# edd:run — scenarios → traces → scores

Inner loop of the eval pipeline. Covers Mode 1 (quick analysis) and Mode 2 Phase 1 (score table).

## Preconditions

- `.edd/session.json` exists with `mode` + `aggression` (router writes this — if missing, ask)
- `regressions.txt` exists ([`edd:scope-agent`](../scope-agent/SKILL.md))
- For Mode 1: none beyond the above
- For Mode 2: judges in Opik ([`edd:scope-evals`](../scope-evals/SKILL.md)); enrichment script in `_local/` if your trace shape needs it
- venv active: `source scripts/.venv/bin/activate`
- `edd check` passes
- **On a feature branch, not `main` / `master`.** `edd run` refuses to emit traces from the default branch — prevents `sim-main` taint. If you intentionally want main, pass `--allow-main`.

## Step 1 — Generate scenarios

Read `.edd/session.json` for `aggression`. Follow [references/scenario-design.md](../../references/scenario-design.md):

- aggression `1` — harness validation, exact trigger phrases
- aggression `2` — level 1 + edge cases (empty results, adjacent intents, partial triggers)
- aggression `3` — adversarial, mostly edge cases

Generate 5–10 scenarios for the diff. Write to `scenarios.txt` at repo root. One scenario per line — plain string or JSON with optional `context`, `followups`, `evaluators`.

Do not duplicate `regressions.txt`. Scenarios target what the diff touches; regressions cover baseline promises.

## Step 2 — Branch on mode

### Mode 1 — Quick trace analysis (no judges)

```bash
edd run scenarios.txt   # emit + tag, no judging
```

Then fetch and report inline:

```python
import sys; sys.path.insert(0, 'scripts')
from shared.opik_client import OpikClient
c = OpikClient()
traces = c.search_traces(project, from_time='<since>')
for t in traces:
    inp = t.get('input') or {}
    out = t.get('output') or {}
    meta = t.get('metadata') or {}
    # Path varies by SDK — see references/trace-inspection.md
    # Agno/OpenInference:  inp.get('input.value'), out.get('output.value')
    # Anthropic SDK:       inp.get('message'), out.get('output')
    # OpenAI Agents SDK:   inp.get('input',[{}])[0].get('content')
    # After enrichment:    meta.get('user_message'), meta.get('assistant_response')
    print(t['id'][:8], str(inp)[:80])
    print(' ->', str(out)[:160])
    print('  tools:', meta.get('tools_called', []))
```

Report findings in conversation. **Stop** unless the user asks for Mode 2 or 3.

### Mode 2 Phase 1 — Score with judges

Branch on whether enrichment is required (check `.edd/evaluator-plan.md` — if judges read `metadata.user_message` etc., yes):

**No enrichment needed (simple agents):**
```bash
edd run scenarios.txt --wait --evaluators "<name-a>,<name-b>"
```

**With enrichment (most multi-SDK runtimes):**
```bash
edd run scenarios.txt                                            # emit + tag, exit
python _local/enrich_traces_<sdk>.py --since-minutes 5           # SDK-specific
edd score --since 10 --evaluators "<name-a>,<name-b>"            # trigger + poll + print
```

Pick the enrichment script matching the SDK:
- `enrich_traces.py` — Agno
- `enrich_traces_claude.py` — Anthropic SDK
- `enrich_traces_openai.py` — OpenAI Agents SDK

The CLI tags every trace `sim-<branch>` — that tag is the join key for [`edd:experiment`](../experiment/SKILL.md).

## Step 3 — Read the table

Below 0.5 = real failure. Red cells print the judge's reason inline. See [references/score-reading.md](../../references/score-reading.md) for thresholds, judge biases, and non-determinism rules.

For each red row:
1. Open the trace at the printed Opik URL
2. Classify via [references/failure-modes.md](../../references/failure-modes.md):
   - **prompt issue** → fix prompt/skill/tool, re-run
   - **dataset issue** → patch scenario, re-run
   - **evaluator issue** → recalibrate judge (back to [`edd:scope-evals`](../scope-evals/SKILL.md))
   - **flaky / model-bound** → tag and skip

## Step 4 — Stop condition

- Mode 1: stop after reporting trace findings.
- Mode 2: stop when the table is green. Otherwise apply the [stopping rules](../CLAUDE.md#stopping-rules).

For most branch-level work, the inner loop is enough. Escalate to [`edd:experiment`](../experiment/SKILL.md) only when you need a durable record across time/people.

## Anti-patterns

- Picking every judge — irrelevant judges drown signal with neutral 0.5s. Pick the ones the diff exercises.
- Skipping enrichment when judges read `metadata.*` — judges get 0 because the paths are empty, not because the agent failed.
- Editing scenarios mid-loop without re-running — last-write wins, prior scores stale.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global).

## Next

- Mode 1 → done
- Mode 2 + need a durable scoreboard → [`edd:experiment`](../experiment/SKILL.md)
- Mode 3 + want to optimize one judge → [`edd:optimisation`](../optimisation/SKILL.md)
