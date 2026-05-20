# skills/ — sitemap

Eval-Driven Development is split into a router + five focused sub-skills. Each `SKILL.md` is loaded only when its description matches; pick the right one to keep context lean.

## Sub-skill index

| Skill | When to invoke | Outputs |
|---|---|---|
| [`edd:edd`](edd/SKILL.md) | top-level entry — user wants an eval workflow without naming a phase | `.edd/session.json`, dispatch to one below |
| [`edd:scope-agent`](scope-agent/SKILL.md) | new agent, or agent source changed | `.edd/promises.md`, `regressions.txt` |
| [`edd:scope-evals`](scope-evals/SKILL.md) | promise inventory exists but Opik project lacks the judges | `.edd/evaluator-plan.md`, `_local/create_evaluators.py`, judges in Opik |
| [`edd:run`](run/SKILL.md) | Mode 1 (quick analysis, judges optional) or Mode 2 Phase 1 (emit + tag + smoke-judge-check) | `scenarios.txt`, sim-tagged traces, inline trace report (+ optional Mode 1 score table) |
| [`edd:experiment`](experiment/SKILL.md) | Mode 2 Phase 2 — durable dataset + experiment, **sole judge plane** for comparison | Opik dataset (`<project>-<topic>-v<N>`), experiment with scorecard |

## Pipeline DAG

```
scope-agent ──► scope-evals ──► run ──► experiment Phase D (build dataset)
                                  │                  │
                                  │                  └──► experiment Phase E (judge) ──► inspect
                                  │
                                  └─► (stop here for Mode 1 / most branch work)
```

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
- **`edd:experiment` before `edd:run` smoke check passes.** Judges that don't land on 5 traces won't land on 500 — verify cheap, scale once.
- **Iterating Mode 2 on the trace-plane score table.** Mode 2's comparison plane is the experiment, not the trace. Inner loop is emit + smoke-only.
- **Dataset rewrite in place.** New item shape ⇒ new version. Cross-version comparisons are noise.

## Stopping rules

- **Two prompt iterations on the same red judge ⇒ stop tweaking, widen the search.** The next thing to question is the evaluator, the dataset, or the underlying behavior model — not the prompt phrasing. See [`references/failure-modes.md`](../references/failure-modes.md) for prompt-iteration vs judge-noise distinction. (Applies at the experiment plane in Mode 2; at the inline / `edd score` plane in Mode 1.)
- **Mode 2: smoke check passes ⇒ promote to experiment.** Mode 2's stop signal is "judges land", not "scores are green" — green is what you discover *at* the experiment plane.
- **Mode 1: inline trace findings sufficient ⇒ ship** (or run `edd score` once for a one-shot table).

## Naming conventions

| Artifact | Pattern | Notes |
|---|---|---|
| Branch | `<topic>` (e.g. `url-clarification`) | Branch name = topic = tag. No `feat/` prefix. |
| Trace branch tag | `sim-<topic>` | Auto-stamped by `edd run`; join key for `edd-build`. Single identity tag. |
| Dataset | `<project>-<topic>-v<N>` | Bump `<N>` only when item shape changes |
| Experiment | derived from dataset + variant (`<topic>-baseline`, `<topic>-v2`) | Set via `--experiment-name` |
| Tag pattern | `[sim-<topic>, *extra]` | Branch name carries topic — no separate topic tag. Mode + aggression → `--description`. |

All names are minted at runtime from session state — never pre-planned by the user.

## Reference docs

Each skill points to the subset of [`references/`](../references/CLAUDE.md) it needs. Don't load all of them upfront — they're decision guides, not narrative docs.

## Up one level

- Root: [../CLAUDE.md](../CLAUDE.md) — repo overview, integration contract, layout
