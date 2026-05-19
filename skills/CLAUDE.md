# skills/ — sitemap

Eval-Driven Development is split into a router + five focused sub-skills. Each `SKILL.md` is loaded only when its description matches; pick the right one to keep context lean.

## Sub-skill index

| Skill | When to invoke | Outputs |
|---|---|---|
| [`edd:edd`](edd/SKILL.md) | top-level entry — user wants an eval workflow without naming a phase | `.edd/session.json`, dispatch to one below |
| [`edd:scope-agent`](scope-agent/SKILL.md) | new agent, or agent source changed | `.edd/promises.md`, `regressions.txt` |
| [`edd:scope-evals`](scope-evals/SKILL.md) | promise inventory exists but Opik project lacks the judges | `.edd/evaluator-plan.md`, `_local/create_evaluators.py`, judges in Opik |
| [`edd:run`](run/SKILL.md) | Mode 1 (quick analysis) or Mode 2 Phase 1 (inner loop) | `scenarios.txt`, sim-tagged traces, score table or inline trace report |
| [`edd:experiment`](experiment/SKILL.md) | Mode 2 Phase 2 — durable dataset + experiment in Opik UI | Opik dataset (`<project>-<topic>-v<N>`), experiment with scorecard |
| [`edd:expand`](expand/SKILL.md) | Optional — AI-driven growth of an existing dataset (coverage gaps, adversarial variants) | More items in the seed dataset, targeting the underrepresented bucket |

## Pipeline DAG

```
scope-agent ──► scope-evals ──► run ──► experiment Phase D (build dataset)
                                  │                  │
                                  │                  ├──► expand (optional — AI growth)
                                  │                  │           │
                                  │                  │           ▼
                                  │                  └──► experiment Phase E (judge) ──► inspect
                                  │
                                  └─► (stop here for Mode 1 / most branch work)
```

**Hard ordering rule:** if you're going to expand, do it **before** Phase E. Judging a tiny seed and then expanding wastes LLM spend on a stale-shape scorecard; you'd have to re-judge to compare apples-to-apples. The expand step never sits between two judge runs.

Each downstream skill checks for cached outputs from upstream and skips re-derivation when fresh.

## Shared session state

All sub-skills read/write `.edd/session.json` (gitignored). Keys:

| Key | Set by | Consumed by |
|---|---|---|
| `mode`, `aggression` | router | run, experiment |
| `project` | router (asked) | scope-evals, run, experiment |
| `topic` | router (derived from hypothesis) | experiment (naming) |
| `branch_tag` | router (from git branch) | run, experiment |
| `dataset_name`, `experiment_name` | experiment | inspect / handoff |

## Pipeline anti-patterns

Global rules — apply across every sub-skill. Skill-specific anti-patterns live inside each SKILL.md.

- **Re-deriving cached outputs every session.** `regressions.txt` and Opik judges persist. Check timestamps and re-run scope-* only when source has changed.
- **`edd:experiment` before `edd:run` is green.** Judges that misfire on 5 traces will misfire on 500 — find that out cheap.
- **Dataset rewrite in place.** New item shape ⇒ new version. Cross-version comparisons are noise.

## Stopping rules

- **Two prompt iterations on the same red judge ⇒ stop tweaking, widen the search.** The next thing to question is the evaluator, the dataset, or the underlying behavior model — not the prompt phrasing. See [`references/failure-modes.md`](../references/failure-modes.md) for prompt-iteration vs judge-noise distinction.
- **Score-table green on regressions.txt ⇒ promote to experiment** (Mode 2) **or ship** (Mode 1).

## Naming conventions

| Artifact | Pattern | Notes |
|---|---|---|
| Trace branch tag | `sim-<git-branch>` | Auto-stamped by `edd run`; join key for `edd-build` |
| Dataset | `<project>-<topic>-v<N>` | Bump `<N>` only when item shape changes |
| Experiment | derived from dataset + variant (`<topic>-baseline`, `<topic>-v2`) | Set via `--experiment-name` |

All names are minted at runtime from session state — never pre-planned by the user.

## Reference docs

Each skill points to the subset of [`references/`](../references/CLAUDE.md) it needs. Don't load all of them upfront — they're decision guides, not narrative docs.

## Up one level

- Root: [../CLAUDE.md](../CLAUDE.md) — repo overview, integration contract, layout
