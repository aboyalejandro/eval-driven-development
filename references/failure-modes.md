# Failure modes — red judge → likely fix surface

When a judge scores below 0.5, this doc tells you (a) whether the red is real, (b) where the cause most likely lives, and (c) when to stop tweaking. Read it *while* staring at a red cell. For the score-table mechanics see [`scoring.md`](scoring.md).

## Before you fix anything — rule out judge issues

A red cell is not yet a confirmed regression. Three things can make a judge fire incorrectly.

### Judge biases

LLM-as-judge evaluators have systematic biases — three to know:

- **Verbosity bias** — longer responses score higher on relevance/helpfulness even when they're padded. If a format-tightening change makes a relevance score drop, the trace probably got shorter and the judge confused brevity with incompleteness.
- **Self-preference** — judges score outputs from the same model family higher. If you swap from Claude to GPT and faithfulness drops 0.05 across every trace with no visible response change, it's likely judge bias, not a real regression.
- **Refusal penalty** — judges sometimes mark legitimate refusals (write-confirmation prompts, "I can't access that data") as failures on helpfulness. Cross-check with the safety/recovery judges before reading too much into a single low score.

When two judges disagree on the same trace (one red, one green on overlapping dimensions), the trace usually tells you which is right.

### Judge non-determinism

LLM-as-judge scores are not fully deterministic, even at `temperature=0`. The same trace, same rubric, same model can flip between runs on edge cases.

- **One red ≠ confirmed failure.** Re-run the same scenarios once before acting. If the red holds across two independent runs, it's real signal.
- **A flicker (red one run, green the next) is noise**, not a regression. Note it and move on unless it persists across three runs.
- **Stable reds across two or more runs are actionable** — that's the judge consistently flagging the same behavior.
- **Deltas are more reliable than absolutes.** If a prompt change moves a judge from 0 to 1 *and holds across two re-runs*, the change worked.

### What the score can't tell you

The score points; the trace explains. Before tweaking the prompt, open the trace and figure out which of these the red actually is:

- **Real prompt regression** — the agent did the wrong thing
- **Tool failure** — the tool call returned an error or wrong shape; the agent had nothing good to work with
- **Judge bias** — the judge misread the trace (rare, but real — see above)
- **Scenario mismatch** — the scenario didn't actually exercise what you thought it did

## Symptom → fix surface

Once you've ruled out judge issues and confirmed the red is real, map the symptom to the most common cause. The "Evaluator family" column is a descriptor, not a name — your project's evaluators will have agent-specific names derived from `agent-analysis.md`. Match on the symptom, not on the label.

| Symptom in trace | Evaluator family | Likely cause | First place to look |
|-----------------|-----------------|--------------|---------------------|
| Response shape regressed — sections missing, wrong format | Format | Prompt edit shifted the output spec | The format/output section of the system prompt |
| Agent answered without calling a tool when one was needed | Tool selection | Tool description is too vague, or routing prompt downgrades it | Tool docstring + tool-routing prompt section |
| Tool was called but with wrong or missing params | Tool selection | Schema description doesn't surface valid values | Tool parameter descriptions (the `Args:` block) |
| Empty search → agent hallucinated or made up an answer | Recovery | Tool docstring doesn't tell the agent what to do on empty results | Tool docstring "if no results" guidance |
| Agent answered from training data instead of fetched context | Grounding | Retrieval missed, or prompt doesn't anchor to retrieved content | Retrieval config + grounding section of system prompt |
| Correct skill didn't trigger, or wrong skill triggered | Routing | Trigger words overlap with another skill, or routing prompt weakened | Skill trigger description + routing section |
| Agent used default terms instead of configured ones | Terminology | Custom vocabulary not injected into context | Context-injection layer |
| Destructive action ran without confirmation | Safety | Confirmation prompt section weakened or skipped | Safety/confirmation section of system prompt |
| Raw error or stack trace leaked to user | Error handling | Tool wrapper not catching/translating errors | Tool error-handling layer — not the prompt |
| Follow-up suggestions missing or generic | Output contract | Action-suggestion rule weakened | Action-suggestion section in system prompt |

## When the table doesn't help

If none of the above fits, two questions:

1. **Did the right tool calls happen at all?** Open the trace tree. If the tool surface is broken (missing call, error, wrong shape), no prompt fix will repair it.
2. **Is the judge actually right?** Re-read the judge biases above and check the rubric against the trace.

## Simulation-only failure modes

These don't show up in the setup loop — they only surface once an
experiment exists, because they're failures of the dataset / experiment
plumbing rather than the agent itself.

| Symptom | Cause | Fix |
|---|---|---|
| Experiment items table shows zero scores even though traces have scores | Trigger lands scores on traces; items table is a separate copy | `edd-run` polls trace scores and copies them to items — if you re-score outside the script, mirror the same poll-and-copy |
| Scores moved but the dataset shape stayed identical | Dataset version drifted under the optimization | Pin `dataset_version_id` per experiment, or bump the dataset name and start a new optimization |
| Optimization timeline shows experiments with very different N | Some runs hit a truncated trace window | Widen `--from` on `edd-build`, or build the dataset once and reuse for every experiment in the optimization |
| Inspect digest has no rows | The dataset items lack `source_trace_id` (extractor dropped it) | Rebuild with a working extractor; verify with `edd-build --dry-run` first |

## Two failed iterations on the same dimension

If you've tweaked the prompt twice and the same judge stays red, **stop tweaking the prompt**. The cause is almost certainly:

- Tool surface broken (run the raw API/wrapper test before the next eval run)
- Judge miscalibration (file a calibration ticket, run with the judge excluded)
- Wrong scenario (the scenario doesn't actually exercise the path you think it does)

Two strikes on a prompt edit is a signal to widen the search, not narrow it further.

**Important distinction — prompt iterations vs. re-runs.** The "two strikes" rule counts *distinct prompt edits*, not repeat runs of the same trace. Apply the non-determinism rules above before counting a red as a strike: re-run the scenario once unchanged; only count the strike if the red holds across both runs.

## Anti-patterns

- **Tweaking the prompt before opening the trace.** The score points; the trace explains. Reading the score alone almost always sends you to the wrong fix surface.
- **Treating a single red as a regression.** Re-run once before acting — judge non-determinism flips edge-case scores between runs.
- **Counting a flicker as a strike** in the two-iterations rule. Strikes count *stable* reds across re-runs, not first-time reds.
- **Fixing the prompt when the tool surface is broken.** No prompt edit repairs a missing tool call, wrong params, or an upstream API error. Check the trace tree first.
- **Filing a judge as miscalibrated on one trace.** Calibration claims need ≥3 traces where the rubric disagrees with the actual content.

## See also

- [`scoring.md`](scoring.md) — score-table mechanics + the "0 = not applicable" convention
- [`evaluator-selection.md`](evaluator-selection.md) — when "judge miscalibrated" is the right classification
- [`../skills/run/SKILL.md`](../skills/run/SKILL.md) — inner-loop stop rules
- [`../skills/experiment/SKILL.md`](../skills/experiment/SKILL.md) — same failure-mode taxonomy applies at experiment scale
