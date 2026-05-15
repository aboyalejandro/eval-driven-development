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

## Reading the trace, not just the score

The score points; the trace explains. Always open the trace for any red cell before tweaking the prompt — the score alone won't tell you whether the failure is:

- **Real prompt regression** — the agent did the wrong thing
- **Tool failure** — the tool call returned an error or wrong shape, agent had nothing good to work with
- **Judge bias** — the judge misread the trace (rare, but real)
- **Scenario mismatch** — the scenario didn't actually exercise what you thought it did

You can't tell which from the score. Open the trace tree, read the tool calls, read the response.

## Common judge biases to watch for

LLM-as-judge evaluators have systematic biases. Three to know:

- **Verbosity bias** — longer responses score higher on relevance/helpfulness even when they're padded. If a format-tightening change makes a relevance score drop, the trace probably got shorter and the judge confused brevity with incompleteness.
- **Self-preference** — judges score outputs from the same model family higher. If you swap from Claude to GPT and faithfulness drops 0.05 across every trace with no visible response change, it's likely judge bias, not a real regression.
- **Refusal penalty** — judges sometimes mark legitimate refusals (write-confirmation prompts, "I can't access that data") as failures on helpfulness. Cross-check with the safety/recovery judges before reading too much into a single low score.

When two judges disagree on the same trace (one red, one green on overlapping dimensions), the trace usually tells you which is right.

## When the same judge stays red across iterations

If you tweak the prompt twice and the same judge stays below 0.5, stop tweaking. The cause is probably not in the prompt:

1. Open the trace and check whether the right tool calls happened at all.
2. If the tool surface is wrong (missing call, wrong params, error response), no prompt fix will repair it.
3. If the tool surface is correct, the judge may be miscalibrated — check its rubric against the trace, file a calibration ticket if it's truly wrong.

Two failed iterations on the same dimension is a signal to widen the search, not to keep narrowing the prompt.

## Judge non-determinism

LLM-as-judge scores are not fully deterministic, even at `temperature=0`. The same trace, same rubric, same model can flip between runs — 0 → 1 or 1 → 0 — on edge cases where the response is near the rubric boundary.

Practical rules:

- **One red ≠ confirmed failure.** Re-run the same scenarios once before acting. If the red holds across two independent runs, it's real signal.
- **A score that flickers (red one run, green the next) is noise**, not a regression. Note it and move on unless it persists across three or more runs.
- **Stable reds across two or more runs are actionable** — that's the judge consistently flagging the same behavior.
- **Deltas are more reliable than absolutes.** If a prompt change moves a judge from 0 to 1 *and holds across two re-runs*, the change worked. A one-run flip is noise.

## Comparing runs

Tag the run id and branch so you can compare tables across iterations in the Opik UI. The score delta between two runs of the same scenarios is the cleanest signal — absolute scores depend on judge calibration, but deltas catch real regressions.
