# references/ — decision guides

Standalone markdown files. **Decision aids, not narrative docs** — each skill loads only the subset it needs at the moment it needs it.

## Files

| File | When to load | Used by skill |
|---|---|---|
| `agent-analysis.md` | extracting promise inventory from agent source | [`edd:scope-agent`](../skills/scope-agent/SKILL.md) |
| `evaluator-selection.md` | mapping promises → judge dimensions; picking the target evaluator for an experiment | [`edd:scope-evals`](../skills/scope-evals/SKILL.md), [`edd:experiment`](../skills/experiment/SKILL.md) |
| `scenario-design.md` | drafting `scenarios.txt` at a chosen aggression level | [`edd:scope-agent`](../skills/scope-agent/SKILL.md), [`edd:run`](../skills/run/SKILL.md) |
| `trace-inspection.md` | discovering your trace shape (per-SDK conventions, quick-start) | [`edd:scope-evals`](../skills/scope-evals/SKILL.md), [`edd:run`](../skills/run/SKILL.md) |
| `trace-enrichment.md` | writing `_local/enrich_traces_<sdk>.py` once shape is known (Pattern A/B, skeleton) | [`edd:run`](../skills/run/SKILL.md) |
| `score-reading.md` | reading the score table (thresholds, the "0 = not applicable" convention, run-comparison) | [`edd:run`](../skills/run/SKILL.md) |
| `failure-modes.md` | red judge → real-vs-noise check (biases, non-determinism) and symptom → fix-surface map | [`edd:run`](../skills/run/SKILL.md), [`edd:experiment`](../skills/experiment/SKILL.md) |
| `dataset-design.md` | item shape, coverage targets, naming `<project>-<topic>-v<N>` | [`edd:experiment`](../skills/experiment/SKILL.md) |
| `opik-endpoints.md` | REST scripts erroring on Opik API drift | [`shared/opik_client.py`](../scripts/shared/CLAUDE.md) |
| `agent-pr-process.md` | creating a PR on the agent repo using EDD findings (hypothesis → branch → change → PR) | manual / cross-session recovery |

## Naming

All references follow `<domain>-<aspect>.md` — lowercase kebab-case, single hyphen.

- **`<domain>`** = the pipeline noun (`agent`, `scenario`, `evaluator`, `trace`, `dataset`, `experiment`, `score`, `failure`, `opik`)
- **`<aspect>`** = the act or facet (`-analysis`, `-design`, `-selection`, `-grouping`, `-inspection`, `-enrichment`, `-reading`, `-modes`, `-endpoints`)

Reads as a sentence: `trace-enrichment.md` = "trace enrichment", `score-reading.md` = "score reading".

No format suffixes (`-cheatsheet`, `-guide`) — content type is implicit. Every reference is a decision guide.

## Load order

There is no canonical order — load the file that matches the question you have right now. Common patterns:

| Question | Load |
|---|---|
| "What does this agent actually promise?" | `agent-analysis.md` |
| "Which judge applies to this promise?" | `evaluator-selection.md` |
| "Why is this judge red? / is this red real?" | `failure-modes.md` (then `score-reading.md` for table mechanics) |
| "What's in `trace.output.value` for this SDK?" | `trace-inspection.md` |
| "How do I normalize that into `metadata.*`?" | `trace-enrichment.md` |
| "Is `v2` of this dataset different enough to warrant a new version?" | `dataset-design.md` |
| "Opik just returned 404 on this endpoint" | `opik-endpoints.md` |
| "How do I open a PR on the agent repo with EDD results?" | `agent-pr-process.md` |

## Up one level

- Root: [../CLAUDE.md](../CLAUDE.md)
- Skills: [../skills/CLAUDE.md](../skills/CLAUDE.md)
