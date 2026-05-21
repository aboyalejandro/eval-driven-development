# Eval-Driven Development for LLM Agents

> ⚠️ **Active development.** APIs, skill bodies, and CLI flags will change without notice. **No remote/registry install yet.** Install locally as a Claude Code plugin — see [`DEVELOPMENT.md`](DEVELOPMENT.md). Pin to a commit if you need stability.

Tests tell you code runs. They don't tell you the agent is still good at its job.

A prompt edit that fixes one behavior breaks three others silently. A model swap shifts response shape. Tool routing drifts after a schema change. None of this surfaces in CI — and most eval platforms can't catch it either, because they replay inputs against a prompt without running the real toolkit.

EDD closes the gap: run the live agent against real scenarios, capture every tool call, score with judges that see what the agent actually did.

## How it works

Three primitives — headless runner, traces, judges — composed into two loops:

```text
inner loop  (minutes):  run scenarios → score traces → read table → fix or ship
outer loop  (hours+):   curate dataset → run experiment → compare on timeline → keep or roll back
```

The runner invokes the agent over HTTP. The agent emits traces to Opik directly. EDD reads those traces via REST, tags them by branch, enriches metadata, and fires judges against exactly the traces it just ran — not auto-sampled noise from the rest of the project.

## Skill decision flow

Invoke `/edd` and it dispatches based on current state. Or call sub-skills directly when you know the phase.

```text
              ┌──────────────────────────────────────────┐
              │                  /edd                    │
              │      reads .edd/session.json             │
              └──────────────────┬───────────────────────┘
                                 │
         ┌───────────────────────▼──────────────────────┐
         │    new agent or promises changed?             │
         └───────────────────────┬──────────────────────┘
                  yes            │              no
                   ▼             │
          ┌──────────────┐       │
          │ scope-agent  │       │
          │ promises.md  │       │
          │ regressions  │       │
          └──────┬───────┘       │
                 └───────────────┘
                                 │
         ┌───────────────────────▼──────────────────────┐
         │                which mode?                    │
         └──────────────┬───────────────────────────────┘
                        │
            ┌───────────┴────────────────┐
            │                            │
         Mode 1                       Mode 2
            │                            │
      scope-evals                  scope-evals
      optional — only if           required:
      inline scoring needed        judges missing or
                                   promises changed
            │                            │
          run                          run
       emit scenarios              emit scenarios +
       inline score table          smoke-check 3–5 traces
            │                            │
          done                    experiment Phase D
                                  build dataset from traces
                                          │
                                 ┌────────▼────────┐
                                 │ coverage thin?  │
                                 └────────┬────────┘
                                  yes     │      no
                                   ▼      │
                                 expand   │   ← hard gate before judging
                                   └──────┘
                                          │
                                  experiment Phase E
                                  judge — sole scoring plane
                                          │
                                       inspect
```

| Skill | Trigger | Key outputs |
| --- | --- | --- |
| `edd:edd` | user wants eval workflow, no phase named | `.edd/session.json`, dispatches below |
| `edd:scope-agent` | new agent or source changed | `promises.md`, `regressions.txt` |
| `edd:scope-evals` | judges missing in Opik **or** promises changed; optional in Mode 1 (only if inline scoring), required in Mode 2 | `evaluator-plan.md`, judges in Opik |
| `edd:run` | Mode 1 (quick) or Mode 2 Phase 1 (emit + tag) | `scenarios.txt`, branch-tagged traces, inline scores |
| `edd:experiment` | Mode 2 Phase 2 — build dataset (Phase D) then judge (Phase E) | Opik dataset + experiment scorecard |
| `edd:expand` | between Phase D and E if dataset coverage is thin — hard gate, never skip | expanded dataset with broader scenario coverage |

## Why not synthetic datasets?

Synthetic datasets give you input → output pairs. That's enough to score text quality — not enough to score agent behavior.

Did the agent call the right tool? Handle an empty result? Respect scope when the user pushed? Those questions require a full trace: tool calls, arguments, intermediate outputs. A synthetic dataset has none of that, because the trace never happened — you handcrafted the input and compared the final response.

EDD builds datasets from real traces. Run the live agent against scenarios, capture what it actually did, then build the dataset from those traces. Judges score the full trace — not a reconstructed approximation of it.

## When to skip it

Pure UI changes, refactors that don't touch prompts or tools, bug fixes with a reproducing unit test. EDD is for the surface where types don't reach.

## Resources

- [DEVELOPMENT.md](DEVELOPMENT.md) — local install: register the plugin, install the CLI, wire env vars.
- [CLAUDE.md](CLAUDE.md) — repo sitemap (skills, scripts, references) + key constraints.
- [skills/CLAUDE.md](skills/CLAUDE.md) — sub-skill index, pipeline DAG, cross-cutting rules.
- [references/CLAUDE.md](references/CLAUDE.md) — decision guides, "load when X" index.
- [PREREQUISITES.md](PREREQUISITES.md) — integration contract + adapter pattern.
