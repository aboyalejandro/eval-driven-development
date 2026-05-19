# scripts/simulation/ — outer loop

Backs `edd-build`, `edd-run`, `edd-inspect`. Promotes sim-tagged traces into a durable dataset, runs experiments against an evaluator, surfaces failures.

## Files

| File | CLI | Role |
|---|---|---|
| `build_dataset.py` | `edd-build` | Sim-tagged traces → Opik dataset items |
| `run_experiment.py` | `edd-run` | Dataset → experiment with judge scores |
| `inspect_experiment.py` | `edd-inspect` | Per-evaluator digest + failure surface |
| `expand_dataset.py` | `edd-expand` | AI-driven dataset growth via Opik `/datasets/expand` |
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

**Tags applied to the experiment:** same shape as `edd-build` — `[branch_tag, *session_tags(), *extra_tag]`.

**Branch-tag warning.** Same `--allow-main` escape hatch as `edd-build`.

## `edd-expand`

AI-driven growth of an existing dataset. Calls Opik's `/datasets/expand` (same primitive as the UI's "Expand with AI" button), receives generated samples, optionally persists via the same write path as `edd-build`.

**Pipeline position is fixed: run `edd-expand` between `edd-build` and `edd-run`, never after.** Judging a thin seed and then expanding wastes LLM judge spend on a stale scorecard you can't compare to the post-expansion one. If you already judged, bump the dataset version and rebuild before expanding.

Required: `--dataset-name`, `--model`, `--count`. Optional steering: `--variation-instructions` (free-form, gap-targeted) or `--custom-prompt` (full prompt override), `--preserve-field` (repeatable — fields whose pattern the LLM must keep). Add `--max-tokens` for Anthropic models.

**Two-step contract** — `--dry-run` prints the first 3 samples to stdout without persisting; re-run without the flag to insert. Always `--dry-run` first; expansion costs LLM tokens and polluted datasets are hard to clean.

The skill [`edd:expand`](../../skills/expand/SKILL.md) reads the seed dataset, the agent's promises, and the evaluator plan, then derives all params from the actual coverage gap. The CLI is mechanical.

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
- Skills that use this: [`edd:experiment`](../../skills/experiment/SKILL.md), [`edd:expand`](../../skills/expand/SKILL.md)
