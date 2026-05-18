# skills/ — sitemap

Eval-Driven Development is split into a router + five focused sub-skills. Each `SKILL.md` is loaded only when its description matches; pick the right one to keep context lean.

## Sub-skill index

| Skill | When to invoke | Outputs |
|---|---|---|
| [`edd:edd`](edd/SKILL.md) | top-level entry — user wants an eval workflow without naming a phase | `.edd/session.json`, dispatch to one below |
| [`edd:scope-agent`](scope-agent/SKILL.md) | new agent, or agent source changed | `.edd/promises.md`, `regressions.txt` |
| [`edd:scope-evals`](scope-evals/SKILL.md) | promise inventory exists but Opik project lacks the judges | `.edd/evaluator-plan.md`, `_local/create_evaluators.py`, judges in Opik |
| [`edd:run`](run/SKILL.md) | Mode 1 (quick analysis) or Mode 2 Phase 1 (inner loop) | `scenarios.txt`, sim-tagged traces, score table or inline trace report |
| [`edd:experiment`](experiment/SKILL.md) | Mode 2 Phase 2 — durable dataset + experiment in Opik UI | Opik dataset (`<project>-<topic>-v<N>`), experiment, optional optimization timeline |
| [`edd:optimisation`](optimisation/SKILL.md) | Mode 3 — targeted prompt optimization against one evaluator | post-fix experiment on a shared optimization timeline (3A) or studio trials (3B) |

## Pipeline DAG

```
scope-agent ──► scope-evals ──► run ──► experiment ──► optimisation
                                  │
                                  └─► (stop here for Mode 1 / most branch work)
```

Each downstream skill checks for cached outputs from upstream and skips re-derivation when fresh.

## Shared session state

All sub-skills read/write `.edd/session.json` (gitignored). Keys:

| Key | Set by | Consumed by |
|---|---|---|
| `mode`, `aggression` | router | run, experiment, optimisation |
| `project` | router (asked) | scope-evals, run, experiment, optimisation |
| `topic` | router (derived from hypothesis) | experiment, optimisation (naming) |
| `branch_tag` | router (from git branch) | run, experiment, optimisation |
| `dataset_name` | experiment | optimisation |
| `experiment_name`, `optimization_name` | experiment, optimisation | inspect / handoff |

## Reference docs

Each skill points to the subset of [`references/`](../references/CLAUDE.md) it needs. Don't load all of them upfront — they're decision guides, not narrative docs.

## Up one level

- Root: [../CLAUDE.md](../CLAUDE.md) — repo overview, integration contract, layout
