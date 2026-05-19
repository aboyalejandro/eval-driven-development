---
name: edd
description: Eval-Driven Development router — picks the mode and dispatches. Asks two questions (mode 1/2, aggression 1/2/3), writes `.edd/session.json`, hands off to one of the phase skills. Use this when the user wants an eval workflow but hasn't named a phase. Skill-specific work belongs in `edd:scope-agent`, `edd:scope-evals`, `edd:run`, `edd:experiment`, or `edd:expand`.
---

# edd — router

Top-level entry. Picks the phase, persists session state, hands off.

## When to invoke

After changes to prompts, tool surface, skills, model routing, or memory injection. Skip for pure UI, refactors that don't touch prompts/tools, or bug fixes with a reproducing unit test.

## Ask the user — two questions only

1. **Mode** — which mode do you want to run?
   - `1` — Quick trace analysis. Emit + tag traces; Claude reads them inline. **Judges optional** via `edd score --evaluators "..."` if the user wants a score table without a dataset → `edd:run`
   - `2` — Dataset + experiment. Emit + tag, build a durable dataset, optional `edd:expand` for coverage, then experiment fires the judges. **Inner loop is emit-only** — the experiment plane is the sole scoring plane (trace-plane scores don't sync — see [`references/opik-endpoints.md#score-storage--two-planes-no-auto-sync`](../../references/opik-endpoints.md#score-storage--two-planes-no-auto-sync)). A 3–5 trace smoke-judge-check runs before the experiment to verify judges land at all → `edd:run` → `edd:experiment`

2. **Aggression level** — how hard should the scenarios push the agent?
   - `1` — Harness validation: normal user flows, exact trigger phrases, happy paths
   - `2` — Mixed: level 1 + edge cases (empty results, adjacent intents, partial triggers)
   - `3` — Adversarial: mostly edge cases designed to surface harness failures

## Persist session state

Write `.edd/session.json` with the keys listed in [`skills/CLAUDE.md`](../CLAUDE.md#shared-session-state). Mint `topic` from the user hypothesis (≤5-word kebab slug); leave `dataset_name` / `experiment_name` null — sub-skills fill those.

## Dispatch table

| Mode | Scope needed first? | Then run | Then |
|---|---|---|---|
| 1 | Light (regressions.txt). Judges only if scoring inline. | `edd:run` (emit + inline read; optional `edd score`) | done |
| 2 | Full (promises + evaluators) | `edd:run` emits + smoke-judge-checks 3–5 traces (harness health, not score iteration) | `edd:experiment` Phase D (build) → [`edd:expand`](../expand/SKILL.md) if coverage thin → `edd:experiment` Phase E (judge — sole judge plane) → inspect. **Expansion is a hard gate before Phase E** — never after. |

**Always check first:**
- `regressions.txt` exists at repo root → scope-agent already done; skip unless agent source changed
- Opik project has the evaluators you'll need (via `shared.opik_client.OpikClient().get_evaluators()`) → scope-evals already done; skip unless promises changed

If either is stale, run `edd:scope-agent` and/or `edd:scope-evals` before `edd:run`.

## Discovery rule — derive, don't ask

Never ask the user for evaluator names, dataset names, or experiment names. Derive them per [naming conventions](../CLAUDE.md#naming-conventions); pull dimensions from `edd:scope-agent` + `edd:scope-evals` outputs.

## Next

- [Sub-skill index + Pipeline DAG](../CLAUDE.md) — sitemap with pipeline overview, anti-patterns, stop-rules, session schema.
