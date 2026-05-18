# Reading the score table

The CLI prints one row per trace, one column per judge. Each cell is a 0–1 score.

## Thresholds

| Score | Meaning | Action |
|-------|---------|--------|
| `< 0.5` | Real failure — judge actively flagged the trace | Open the trace, find the cause, fix |
| `0.5`   | Neutral — judge had no opinion or dimension didn't apply | Ignore. Not a fail. |
| `> 0.5` | Pass on that dimension | Move on |
| `-`     | Judge didn't run on this trace | Check the `--evaluators` flag, or the judge's `enabled` flag |

A run is green when no judge that *should* have an opinion came in below 0.5. Some judges abstaining (0.5) is fine — that's the judge correctly recognising the dimension doesn't apply.

**Binary judges (INTEGER scoring):** if you create LLM-as-judge rules with an INTEGER output schema (0 or 1), you will never see a 0.5 score. Every cell is either 0 (fail) or 1 (pass). The `< 0.5` threshold still works — 0 is below it — but the abstain semantics don't apply. A `-` in the table means the judge didn't run; a 0 means it ran and failed. There is no middle ground with binary scoring.

## Reading the trace, not just the score

The score points; the trace explains. Always open the trace for any red cell before tweaking the prompt — see [`failure-modes.md`](failure-modes.md) for the symptom → fix-surface map and the judge-bias / non-determinism rules that decide whether a red is actionable.

## "0 = not applicable" convention

Some judge rubrics score 0 when a dimension is not exercised by the trace, rather than defaulting to 1. This makes 1 meaningful: every cell that reads 1 was explicitly verified as correct. A 0 can mean either "failed" or "this trace didn't test this dimension."

**Reading the digest when using this convention:**

An average of `0.10` for `empty-result-recovery` across 10 traces doesn't mean the agent is failing recovery. It likely means 9 traces didn't exercise the dimension (scored 0 = not tested) and 1 trace tested it and passed (scored 1). The average is meaningless as an aggregate.

To get a clean view of a single dimension, filter with `edd-inspect --evaluator <name>` — this shows only the traces that scored below threshold for that judge, with reasons. Ignore the digest average for "not applicable = 0" judges; focus on the individual failures and their reasons.

## Comparing runs

Tag the run id and branch so you can compare tables across iterations in the Opik UI. The score delta between two runs of the same scenarios is the cleanest signal — absolute scores depend on judge calibration, but deltas catch real regressions.
