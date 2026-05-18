# references/ — decision guides

Standalone markdown files. **Decision aids, not narrative docs** — each skill loads only the subset it needs at the moment it needs it.

## Files

| File | When to load | Used by skill |
|---|---|---|
| `agent-analysis.md` | extracting promise inventory from agent source | [`edd:scope-agent`](../skills/scope-agent/SKILL.md) |
| `evaluator-selection.md` | mapping promises → judge dimensions; picking the target evaluator for an experiment | [`edd:scope-evals`](../skills/scope-evals/SKILL.md), [`edd:experiment`](../skills/experiment/SKILL.md) |
| `scenario-design.md` | drafting `scenarios.txt` at a chosen aggression level | [`edd:scope-agent`](../skills/scope-agent/SKILL.md), [`edd:run`](../skills/run/SKILL.md) |
| `trace-inspection.md` | discovering trace shape; designing `_local/enrich_traces_<sdk>.py` | [`edd:run`](../skills/run/SKILL.md) |
| `scoring.md` | reading the score table, judge biases, non-determinism rules | [`edd:run`](../skills/run/SKILL.md) |
| `failure-modes.md` | classifying a red judge → prompt / dataset / evaluator / flaky | [`edd:run`](../skills/run/SKILL.md), [`edd:experiment`](../skills/experiment/SKILL.md), [`edd:optimisation`](../skills/optimisation/SKILL.md) |
| `dataset-design.md` | item shape, coverage targets, naming `<project>-<topic>-v<N>` | [`edd:experiment`](../skills/experiment/SKILL.md) |
| `experiment-grouping.md` | when to wrap experiments under an Optimization timeline | [`edd:experiment`](../skills/experiment/SKILL.md), [`edd:optimisation`](../skills/optimisation/SKILL.md) |
| `opik-endpoint-cheatsheet.md` | REST scripts erroring on Opik API drift | [`shared/opik_client.py`](../scripts/shared/CLAUDE.md) |

## Load order

There is no canonical order — load the file that matches the question you have right now. Common patterns:

| Question | Load |
|---|---|
| "What does this agent actually promise?" | `agent-analysis.md` |
| "Which judge applies to this promise?" | `evaluator-selection.md` |
| "Why is this judge red?" | `scoring.md` then `failure-modes.md` |
| "What's in `trace.output.value` for this SDK?" | `trace-inspection.md` |
| "Is `v2` of this dataset different enough to warrant a new version?" | `dataset-design.md` |
| "Should baseline and post-fix share an Opik optimization?" | `experiment-grouping.md` |
| "Opik just returned 404 on this endpoint" | `opik-endpoint-cheatsheet.md` |

## Up one level

- Root: [../CLAUDE.md](../CLAUDE.md)
- Skills: [../skills/CLAUDE.md](../skills/CLAUDE.md)
