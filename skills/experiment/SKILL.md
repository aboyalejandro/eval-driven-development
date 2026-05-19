---
name: experiment
description: Promote sim-tagged traces into a durable Opik dataset + experiment with a UI scorecard. Outer loop of the eval pipeline. Use when the score must outlive the branch — cross-time comparison, reviewer handoff. Invoke as `edd:experiment` or when the user says "build dataset", "run experiment", "scoreboard in Opik UI", "outer loop".
---

# edd:experiment — dataset → experiment → inspect

Mode 2 Phase 2 of the eval pipeline. Promotes the inner-loop score into a durable artifact.

## Preconditions

- `.edd/session.json` has `project` and `branch_tag` (`sim-<git-branch>`)
- `.edd/evaluator-plan.md` exists ([`edd:scope-evals`](../scope-evals/SKILL.md))
- Inner loop is **green** ([`edd:run`](../run/SKILL.md)) — judges fire cleanly on a few traces
- Sim batch tagged in the last few hours (re-run `edd:run` if stale)
- venv active

## When to invoke

- comparing two prompt variants on the same inputs
- iterating across days and needing a persistent scorecard
- handing the score off to a reviewer who wasn't in the inner loop

## Phase A — Pick the evaluator

Read `.edd/evaluator-plan.md`. Pick the single dimension that the diff most directly exercises (you can add more evaluators to the experiment run later — start with one). Consult [references/evaluator-selection.md](../../references/evaluator-selection.md) if uncertain.

The chosen evaluator's schema **name** (not id) flows through every later command.

## Phase B — Design the dataset

Follow [references/dataset-design.md](../../references/dataset-design.md). Decide:

- naming per [conventions](../CLAUDE.md#naming-conventions) — read `project` + `topic` from session, start at `v1`, bump when the item shape changes
- coverage mix — every promise represented; aggression-1 + 2 mix unless the experiment specifically targets adversarial
- whether metadata propagates through the trace (rare — usually trace input/output is enough)

Write `dataset_name` to `.edd/session.json`.

## Phase C — Tag a sim batch

If the last `edd:run` was less than ~6h ago you can reuse those traces. Otherwise re-run [`edd:run`](../run/SKILL.md) with full enrichment — judges in the experiment read the same paths they used in the inner loop.

## Phase D — Build the dataset

```bash
edd-build \
  --project <opik-project> \
  --dataset-name <dataset_name> \
  --description "<one-line summary — topic + hypothesis>" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
  --from "$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ)" \
  [--tag <extra-tag>] \
  [--extractor _local.my_extractor:extract] \
  --dry-run
```

`--description` is required (Opik dataset card uses it). `--dry-run` first — verify item count and shape, then re-run without it.

Default extractor reads `metadata.user_message` + `metadata.assistant_response`. Supply `--extractor module:function` if your runtime emits trace paths that differ.

**Tags auto-applied:** `--branch-tag` + `topic` / `mode` / `aggression` from `.edd/session.json` + any `--tag` you pass. Branch-tag warning prints if it references `main`/`master` — pass `--allow-main` to silence.

## Phase E — Run the experiment

```bash
edd-run \
  --project <opik-project> \
  --dataset-name <dataset_name> \
  --evaluator "<schema-name-a>,<schema-name-b>" \
  --description "<hypothesis — what changed and what we expect>" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
  [--tag <extra-tag>] \
  [--score-timeout 300] \
  [--dry-run]
```

`--description` is required and surfaces on the Opik experiment card.

This:
1. Triggers each evaluator on every linked trace
2. Polls scores until done or timeout
3. Creates the experiment with model + branch + evaluator metadata
4. Copies scores onto experiment items

Write `experiment_name` to `.edd/session.json`.

## Phase F — Inspect + iterate

```bash
edd-inspect \
  --experiment-name <experiment_name> \
  [--score-threshold 0.5] \
  [--evaluator "<Schema Name>"] \
  [--out-jsonl /tmp/exp.jsonl]
```

Prints a per-evaluator digest + every failure below threshold with trace links.

Classify failures via [references/failure-modes.md](../../references/failure-modes.md):

| Class | Action |
|---|---|
| prompt issue | fix prompt/skill/tool, re-run Phase E against the same dataset for a fresh experiment |
| dataset issue | patch scenarios, rebuild dataset (Phase D), **new version** — bump `v<N>` |
| evaluator issue | back to [`edd:scope-evals`](../scope-evals/SKILL.md), recalibrate, re-run Phase E |
| flaky / model-bound | tag and skip |

Apply the [stopping rules](../CLAUDE.md#stopping-rules) — two prompt iterations on the same red judge ⇒ widen the search.

## Anti-patterns

- Running an experiment without an evaluator — "I want a scoreboard" is not an evaluator; pick the dimension first.
- Skipping `--dry-run` — bad extractor + real write = polluted dataset.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global rules, including dataset rewrite-in-place).

## Next

→ Inspect digest surfaces persistent failures on one dimension → fix the prompt / dataset / evaluator and re-run Phase E for a fresh comparison experiment.
