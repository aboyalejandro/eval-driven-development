---
name: run
description: Fire scenarios at the agent. Mode 1 emits + tags traces for inline Claude analysis, with optional `edd score` to run judges and print the per-dimension table. Mode 2 emits + tags only — judges fire in `edd:experiment`, not here. A small smoke-judge-check (3–5 traces) verifies judges land before scaling. Generates `scenarios.txt` at session aggression level; branches on whether trace enrichment runs between emit and the smoke check. Invoke as `edd:run` or when the user says "run scenarios", "score traces", "fire judges", "edd inner loop". For *creating* judges, see `edd:scope-evals`.
---

# edd:run — scenarios → traces → (optional) scores

Inner loop of the eval pipeline. Covers Mode 1 (quick analysis, judges optional) and Mode 2 Phase 1 (emit + tag + smoke-judge-check — no score-table iteration).

## Scoring plane recap

The experiment plane is the sole canonical judge plane in Mode 2 — trace-plane and experiment-plane scores are unsynced (see [`references/opik-endpoints.md#score-storage--two-planes-no-auto-sync`](../../references/opik-endpoints.md#score-storage--two-planes-no-auto-sync)). Iterating on a trace-plane score table during the inner loop and then re-firing judges at experiment time wastes spend on stale numbers nobody compares against. The smoke check is a cheap "do judges land at all?" probe, not a score-iteration loop.

## Preconditions

- `.edd/session.json` exists with `mode` + `aggression` (router writes this — if missing, ask)
- `regressions.txt` exists ([`edd:scope-agent`](../scope-agent/SKILL.md))
- For Mode 1: none beyond the above
- For Mode 2: judges in Opik ([`edd:scope-evals`](../scope-evals/SKILL.md)); enrichment script in `_local/` if your trace shape needs it
- venv active: `source scripts/.venv/bin/activate`
- `edd check` passes
- **On a feature branch, not `main` / `master`.** `edd run` refuses to emit traces from the default branch — prevents `main`-branch taint on tagged traces. If you intentionally want main, pass `--allow-main`.

## Step 1 — Generate scenarios

Read `.edd/session.json` for `aggression`. Follow [references/scenario-design.md](../../references/scenario-design.md):

- aggression `1` — harness validation, exact trigger phrases
- aggression `2` — level 1 + edge cases (empty results, adjacent intents, partial triggers)
- aggression `3` — adversarial, mostly edge cases

Generate 5–10 scenarios for the diff. Write to `scenarios.txt` at repo root. One scenario per line — plain string or JSON with optional `context`, `followups`, `evaluators`.

Do not duplicate `regressions.txt`. Scenarios target what the diff touches; regressions cover baseline promises.

## Step 2 — Branch on mode

### Mode 1 — Quick trace analysis (judges optional)

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

Report findings in conversation. **Optional Mode 1 scoring** — if the user wants a judge-backed score table without promoting to a dataset, run `edd score --since 10 --evaluators "<name-a>,<name-b>"` against the same trace window. Trace-plane scores landed by `edd score` are throwaway by design (won't reach experiment plane). **Stop** unless the user asks for Mode 2.

### Mode 2 Phase 1 — Emit + tag + smoke-judge-check

Mode 2 inner loop does **not** iterate on a score table. The experiment plane (Phase E in [`edd:experiment`](../experiment/SKILL.md)) is the sole judge plane. The inner loop's job is:

1. **Emit** scenarios so traces exist to build a dataset from.
2. **Enrich** if judges read `metadata.*` paths the runtime doesn't emit natively.
3. **Smoke-judge-check** — fire judges on a tiny sample to verify they *land* (no missing variable paths, no "API key not configured" errors). Not for score iteration.

For the smoke check, write a 3–5 line `scenarios.txt` (a subset of `regressions.txt` is fine — one per evaluator dimension is plenty), then:

```bash
edd run scenarios.txt                                            # emit + tag, exit
python _local/enrich_traces_<sdk>.py --since-minutes 5           # if your runtime needs it
edd score --since 10 --evaluators "<name-a>,<name-b>"            # triggers + polls; bounded by the recent emit window
```

Sample size is bounded by `scenarios.txt`, not by a `--limit` flag on `edd score` (none exists). Keep `scenarios.txt` small for the smoke; expand it once you regenerate for the experiment.

Pick the enrichment script matching the SDK:
- `enrich_traces.py` — Agno
- `enrich_traces_claude.py` — Anthropic SDK
- `enrich_traces_openai.py` — OpenAI Agents SDK

The CLI tags every trace `<branch>` — that tag is the join key for [`edd:experiment`](../experiment/SKILL.md).

**Smoke-check pass criteria** — each judge in the plan emitted a non-null score on at least one trace within the score timeout. If anything is silent, fix it now: check `/automations/evaluators/{id}/logs`, re-run enrichment, recalibrate the rubric. Cheaper than discovering it on a 200-trace experiment.

**If the smoke check passes, you do not iterate the inner loop further.** Go to [`edd:experiment`](../experiment/SKILL.md) where the dataset gets built and the experiment plane becomes the comparison surface.

## Step 3 — Interpret what the run produced

**Mode 1 inline trace read** — describe what you saw. If the user opted into `edd score` for Mode 1, the table prints; red cells print judge reasons inline. See [`references/score-reading.md`](../../references/score-reading.md) for thresholds and biases. Treat Mode 1 scores as one-shot signal — they don't roll up anywhere.

**Mode 2 smoke check** — only the *landing* of scores matters, not their values. If a judge stayed null on every sample trace, classify via [`references/failure-modes.md`](../../references/failure-modes.md):

- **evaluator issue** (missing variable paths, "no API key configured", rubric returns invalid JSON) → back to [`edd:scope-evals`](../scope-evals/SKILL.md), or fix enrichment, then re-smoke
- **enrichment gap** (judge expects `metadata.X`, enrichment didn't populate it) → fix `_local/enrich_traces_<sdk>.py`, re-enrich, re-smoke
- **flaky / model-bound** → recalibrate judge model in `_local/create_evaluators.py`

Do **not** start tweaking the prompt-under-test from smoke scores — sample size is too small and there's no comparison plane yet.

## Step 4 — Stop condition

- Mode 1: stop after reporting trace findings (and optional one-shot score table).
- Mode 2: stop when the smoke check confirms judges land; the *comparison* happens at the experiment plane.

For most branch-level work that needs a durable record, go straight to [`edd:experiment`](../experiment/SKILL.md) once the smoke check passes.

## Anti-patterns

- Picking every judge — irrelevant judges drown signal with neutral 0.5s. Pick the ones the diff exercises.
- Skipping enrichment when judges read `metadata.*` — judges get 0 because the paths are empty, not because the agent failed.
- **Iterating Mode 2 inner loop on a trace-plane score table.** Mode 2's scoring plane is the experiment, not the trace. Inner loop is emit + smoke-only; comparison happens after `edd:experiment` Phase E.
- **Smoke checking on >20 traces.** It's a landing probe, not a digest. Larger samples burn judge spend for no extra signal.
- Editing scenarios mid-loop without re-running — last-write wins, prior smoke results stale.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global).

## Next

- Mode 1 → done (use `edd score --evaluators "<name>"` for an optional one-shot score table — results stay on the trace plane, no dataset created)
- Mode 2 + smoke check passed → [`edd:experiment`](../experiment/SKILL.md)
