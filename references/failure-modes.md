# Failure modes — red judge → likely fix surface

When a judge scores below 0.5, this table maps the symptom to the most common cause and where to look first. Use it to avoid the trap of tweaking the prompt when the real bug is elsewhere.

Read this *while* staring at a red cell. Cross-reference with `scoring.md` first to rule out judge bias.

The "Evaluator family" column is a descriptor, not a name — your project's evaluators will have agent-specific names derived from `agent-analysis.md`. Match on the symptom, not on the label.

## Symptom → fix surface

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
2. **Is the judge actually right?** Read the trace and the judge's rubric side-by-side. LLM judges sometimes flag legitimate behavior — see `scoring.md` for known biases.

## Layer-2-only failure modes

These don't show up in the inner loop — they only surface once an
experiment exists, because they're failures of the dataset / experiment
plumbing rather than the agent itself.

| Symptom | Cause | Fix |
|---|---|---|
| Experiment items table shows zero scores even though traces have scores | Trigger lands scores on traces; items table is a separate copy | `run_experiment.py` polls trace scores and copies them to items — if you re-score outside the script, mirror the same poll-and-copy |
| Scores moved but the dataset shape stayed identical | Dataset version drifted under the optimization | Pin `dataset_version_id` per experiment, or bump the dataset name and start a new optimization |
| Optimization timeline shows experiments with very different N | Some runs hit a truncated trace window | Widen `--from` on `build_dataset.py`, or build the dataset once and reuse for every experiment in the optimization |
| Inspect digest has no rows | The dataset items lack `source_trace_id` (extractor dropped it) | Rebuild with a working extractor; verify with `--dry-run` first |

## Two failed iterations on the same dimension

If you've tweaked the prompt twice and the same judge stays red, **stop tweaking the prompt**. The cause is almost certainly:

- Tool surface broken (run the raw API/wrapper test before the next eval run)
- Judge miscalibration (file a calibration ticket, run with the judge excluded)
- Wrong scenario (the scenario doesn't actually exercise the path you think it does)

Two strikes on a prompt edit is a signal to widen the search, not narrow it further.
