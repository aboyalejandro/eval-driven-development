# Experiment grouping — when + how

Opik **Optimizations** are containers that group multiple experiments
under one timeline. They're the only way to compare prompt iterations
visually without flipping between detached experiment URLs.

## When to wrap experiments in an optimization

| Use case | Wrap? |
|---|---|
| One-off scoring of a branch's current behavior | **No** — single experiment is enough |
| Comparing two prompt variants against the same dataset | **Yes** — same `--optimization-name`, two `--experiment-name`s |
| Iterating: tweak prompt → re-run → repeat | **Yes** — every run lands on the same timeline |
| HRPO / search-based trial loop | **Yes** — each trial = one experiment, all under the optimization |
| Cross-evaluator comparison on same dataset | **No** — different `objective_name`s don't share a timeline |

## How

Pass `--optimization-name <slug>` to `edd-run`. The script:

1. `find_optimization(name, dataset_id)` — reuses if present
2. Otherwise mints a UUID and `upsert_optimization` with `status=running`
3. Creates the experiment with `optimization_id=<id>` so the timeline
   picks it up

Pass `--finalize-optimization` on the last run to flip status to
`completed`.

## Status flips

| Stage | Status |
|---|---|
| First experiment in a series | `running` |
| Mid-iteration | leave as `running` |
| Final compare run | pass `--finalize-optimization` → `completed` |

A `running` optimization that sits stale forever just clutters the UI;
flip it when the work is done.

## Naming convention

`<topic>-<comparison>` — keeps timelines self-describing.

- `recovery-baseline-vs-v2`
- `format-pre-merge`
- `tool-selection-2026-05-claude-vs-haiku`

Tie the topic to the dataset; tie the comparison to whatever variable
you're moving (prompt version, model, retrieval setting).

## Dataset version pinning

Every experiment under one optimization should hit the same dataset
version, otherwise you're comparing apples to oranges. If you rebuild
the dataset mid-comparison, either:

- Pin `dataset_version_id` on each experiment, or
- Treat the rebuild as a fresh optimization (new name)

Silently letting the dataset drift mid-timeline is the most common cause
of "the score moved but I can't explain why".

## Anti-patterns

- **One optimization spanning unrelated topics.** Recovery and format
  shouldn't share a timeline.
- **Renaming the optimization mid-run.** Breaks the find-or-create lookup
  and you end up with parallel timelines.
- **Skipping the grouping for iteration runs.** You'll re-discover the
  baseline score every time.

## See also

- [`dataset-design.md`](dataset-design.md) — same dataset version across an optimization timeline
- [`failure-modes.md`](failure-modes.md) — sim-only failure modes specific to grouped runs
- [`../skills/experiment/SKILL.md`](../skills/experiment/SKILL.md) — uses `--optimization-name`
- [`../skills/optimisation/SKILL.md`](../skills/optimisation/SKILL.md) — 3A path lives on a single optimization timeline
