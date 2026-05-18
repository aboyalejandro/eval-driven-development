---
description: Eval-Driven Development router — picks the mode and dispatches. Asks two questions (mode 1/2/3, aggression 1/2/3), writes `.edd/session.json`, hands off to one of the phase skills. Use this when the user wants an eval workflow but hasn't named a phase. Skill-specific work belongs in `edd:scope-agent`, `edd:scope-evals`, `edd:run`, `edd:experiment`, or `edd:optimisation`.
---

# edd — router

Top-level entry. Picks the phase, persists session state, hands off.

## When to invoke

After changes to prompts, tool surface, skills, model routing, or memory injection. Skip for pure UI, refactors that don't touch prompts/tools, or bug fixes with a reproducing unit test.

## Ask the user — two questions only

1. **Mode** — which mode do you want to run?
   - `1` — Quick trace analysis (no Opik UI, Claude Code reads traces inline) → `edd:run`
   - `2` — Dataset + experiment (full inner + outer loop, results in Opik UI) → `edd:run` then `edd:experiment`
   - `3` — Optimization run (targeted prompt change → optimization studio) → `edd:optimisation`

2. **Aggression level** — how hard should the scenarios push the agent?
   - `1` — Harness validation: normal user flows, exact trigger phrases, happy paths
   - `2` — Mixed: level 1 + edge cases (empty results, adjacent intents, partial triggers)
   - `3` — Adversarial: mostly edge cases designed to surface harness failures

## Persist session state

Write `.edd/session.json` with the keys listed in [`skills/CLAUDE.md`](../CLAUDE.md#shared-session-state). Mint `topic` from the user hypothesis (≤5-word kebab slug); leave `dataset_name` / `experiment_name` / `optimization_name` null — sub-skills fill those.

## Dispatch table

| Mode | Scope needed first? | Then run | Then |
|---|---|---|---|
| 1 | Light (just regressions.txt) | `edd:run` | done |
| 2 | Full (promises + evaluators) | `edd:run` → score green | `edd:experiment` |
| 3 | Full + one target evaluator | `edd:run` | `edd:optimisation` |

**Always check first:**
- `regressions.txt` exists at repo root → scope-agent already done; skip unless agent source changed
- Opik project has the evaluators you'll need (via `shared.opik_client.OpikClient().get_evaluators()`) → scope-evals already done; skip unless promises changed

If either is stale, run `edd:scope-agent` and/or `edd:scope-evals` before `edd:run`.

## Discovery rule — derive, don't ask

Never ask the user for evaluator names, dataset names, experiment names, or optimization names. Derive them per [naming conventions](../CLAUDE.md#naming-conventions); pull dimensions from `edd:scope-agent` + `edd:scope-evals` outputs.

## See also

- [Sub-skill index + Pipeline DAG](../CLAUDE.md) — sitemap with pipeline overview, anti-patterns, stop-rules, session schema.
