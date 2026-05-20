# scripts/simulation/ — outer loop

Backs `edd-build`, `edd-run`, `edd-inspect`. Promotes sim-tagged traces into a durable dataset, runs experiments against an evaluator, surfaces failures.

## Files

| File | CLI | Role |
|---|---|---|
| `build_dataset.py` | `edd-build` | Sim-tagged traces → Opik dataset items |
| `run_experiment.py` | `edd-run` | Dataset → experiment with judge scores |
| `inspect_experiment.py` | `edd-inspect` | Per-evaluator digest + failure surface |
| `__init__.py` | — | Marker only |

## `edd-build`

Reads traces tagged `--branch-tag sim-<branch>` from `--project`, runs an extractor on each, upserts items into `--dataset-name`.

Default extractor reads `input.message` + `output.output` (native trace fields). Override with `--extractor module:function` for runtimes that emit different shapes (write the function in `_local/<runtime>_extractor.py`). The extractor should also pull `metadata.tools_called` and `metadata.tool_outputs` from enriched traces — see `_local/claude_extractor.py` for the pattern.

**Always `--dry-run` first.** Prints planned items without writing — verify count and shape before committing to a real write.

**Required: `--description "..."`.** Short summary of what the dataset captures (topic + hypothesis). Surfaces on the Opik dataset card and makes datasets searchable later.

**Tags applied to the dataset:** `[branch_tag, *extra_tag]` — branch name = topic = tag. `<topic>` is the single identity tag across traces, dataset, and experiment. Mode and aggression belong in `--description`.

**Branch-tag warning.** Prints a yellow warning when `--branch-tag` references `main` / `master`. Silence with `--allow-main`.

## `edd-run`

Three things in one command:
1. Triggers `--evaluator "<name-a>,<name-b>"` on every trace linked from the dataset.
2. Polls Opik until scores land (`--score-timeout`, default 300s).
3. Creates the experiment with metadata (model, branch, evaluator) and copies scores onto experiment items.

**Required: `--description "..."`.** Surfaces on the Opik experiment card; the hypothesis lives here.

**Tags applied to the experiment:** same shape as `edd-build` — `[branch_tag, *extra_tag]`.

**Branch-tag warning.** Same `--allow-main` escape hatch as `edd-build`.

## Dataset growth

Grow a dataset by running more `edd run` scenarios — new traces → `edd-build` upserts by stable ID (trace ID = item ID). This is the correct Mode 2 path.

Opik's `/datasets/expand` endpoint (`edd-expand`) only supports OpenAI models and generates synthetic items without linked traces, so evaluators cannot score them. Do not use it for trace-based evaluation pipelines.

For generating scenario variations use `_local/expand_with_claude.py` (calls Claude SDK directly, inserts flat items). These items serve as new scenario seeds for the next `edd run` pass — run the agent against them to get real traces, then rebuild.

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
- Skills that use this: [`edd:experiment`](../../skills/experiment/SKILL.md)
