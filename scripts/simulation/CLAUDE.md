# scripts/simulation/ — outer loop

Backs `edd-build`, `edd-run`, `edd-inspect`. Promotes sim-tagged traces into a durable dataset, runs experiments against an evaluator, surfaces failures.

## Files

| File | CLI | Role |
|---|---|---|
| `build_dataset.py` | `edd-build` | Sim-tagged traces → Opik dataset items |
| `run_experiment.py` | `edd-run` | Dataset → experiment (optional `--optimization-name` grouping) |
| `inspect_experiment.py` | `edd-inspect` | Per-evaluator digest + failure surface |
| `__init__.py` | — | Marker only |

## `edd-build`

Reads traces tagged `--branch-tag sim-<branch>` from `--project`, runs an extractor on each, upserts items into `--dataset-name`.

Default extractor reads `metadata.user_message` + `metadata.assistant_response`. Override with `--extractor module:function` for runtimes that emit different paths (write the function in `_local/<runtime>_extractor.py`).

**Always `--dry-run` first.** Prints planned items without writing — verify count and shape before committing to a real write.

**Required: `--description "..."`.** Short summary of what the dataset captures (topic + hypothesis). Surfaces on the Opik dataset card and makes datasets searchable later.

**Tags applied to the dataset:** `[branch_tag, *session_tags(), *extra_tag]` where `session_tags()` reads `.edd/session.json` for `topic`/`mode`/`aggression`, and `--tag <value>` is repeatable.

**Branch-tag warning.** Prints a yellow warning when `--branch-tag` references `main` / `master`. Silence with `--allow-main`.

## `edd-run`

Three things in one command:
1. Triggers `--evaluator "<name-a>,<name-b>"` on every trace linked from the dataset.
2. Polls Opik until scores land (`--score-timeout`, default 300s).
3. Creates the experiment with metadata (model, branch, evaluator) and copies scores onto experiment items.

**Required: `--description "..."`.** Surfaces on the Opik experiment card; the hypothesis lives here.

**Optimization grouping.** `--optimization-name <name>` wraps the experiment under an Opik Optimization so multiple runs appear on one timeline. Pair with `--experiment-name` to label each variant. First call also accepts `--optimization-description` — reused when the same optimization is upserted later. `--finalize-optimization` closes it once you're done iterating. See [`../../references/experiment-grouping.md`](../../references/experiment-grouping.md).

**Tags applied to experiment + optimization:** same shape as `edd-build` — `[branch_tag, *session_tags(), *extra_tag]`.

**Branch-tag warning.** Same `--allow-main` escape hatch as `edd-build`.

## `edd-inspect`

Joins dataset items to experiment outputs and feedback scores. Prints:
- Per-evaluator digest (count, mean, fail rate at `--score-threshold`)
- Every item where any judge scored below threshold, with trace link

Optional `--out-jsonl /tmp/exp.jsonl` for downstream tooling.

## Dataset naming

Convention: `<project>-<topic>-v<N>`. **Bump `<N>` whenever the item shape changes** — cross-version comparisons are noise.

## Module boundaries

All three CLIs go through `shared.opik_client.OpikClient`. Do not call Opik REST directly from this module — add the method to the client if it's missing.

## Up one level

- Engine: [../CLAUDE.md](../CLAUDE.md)
- Skill that uses this: [`edd:experiment`](../../skills/experiment/SKILL.md) (and [`edd:optimisation`](../../skills/optimisation/SKILL.md) for 3A)
