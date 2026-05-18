---
description: Eval-Driven Development router. Ask the user for mode (1/2/3) and aggression (1/2/3), persist to `.edd/session.json`, then delegate to the right sub-skill (`edd:scope-agent`, `edd:scope-evals`, `edd:run`, `edd:experiment`, `edd:optimisation`). Use after any change to prompts, tools, skills, or model routing. Invoke when the user says `/edd`, "run edd", "eval this change", or asks for an eval workflow without naming a phase.
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

Write `.edd/session.json` (gitignored) — every sub-skill reads from here:

```json
{
  "mode": 1,
  "aggression": 2,
  "project": "<opik-project>",
  "branch_tag": "sim-<git-branch>",
  "topic": "<short-slug-of-change>",
  "dataset_name": null,
  "experiment_name": null,
  "optimization_name": null
}
```

Mint `topic` from the user hypothesis (5-word kebab slug). Leave dataset/experiment/optimization null — sub-skills fill those when needed.

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

Never ask the user for evaluator names, dataset names, experiment names, or optimization names. Derive from:

- agent source (skills, system prompt, tool list) → `edd:scope-agent`
- existing Opik evaluators + gaps → `edd:scope-evals`
- session topic + git branch → naming pattern `<project>-<topic>-v<N>`

## Sub-skill index

- [`edd:scope-agent`](../scope-agent/SKILL.md) — extract promise inventory from agent source
- [`edd:scope-evals`](../scope-evals/SKILL.md) — derive evaluator dimensions, list existing, create gaps
- [`edd:run`](../run/SKILL.md) — Mode 1 + Mode 2 Phase 1 (scenarios → traces → score table)
- [`edd:experiment`](../experiment/SKILL.md) — Mode 2 Phase 2 (dataset → experiment → inspect)
- [`edd:optimisation`](../optimisation/SKILL.md) — Mode 3 (3A manual + 3B studio)

## Anti-patterns

- Re-deriving promise inventory every session — check `regressions.txt` first.
- Asking the user for dataset/experiment names — derive them.
- Running `edd:experiment` before `edd:run` is green — judges break at scale, you lose hours.
- Optimization timelines spanning unrelated topics — one optimization name per topic.

## References (load only when relevant)

See [skills/CLAUDE.md](../CLAUDE.md) for the sitemap of `references/*.md` — each sub-skill points to the subset it needs.
