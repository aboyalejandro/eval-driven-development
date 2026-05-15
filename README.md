# Eval-Driven Development for LLM Agents

Tests tell you code runs. They don't tell you the agent is still good at its job.

A prompt edit that fixes one behavior breaks three others silently. A model swap shifts response shape. Tool routing drifts after a schema change. None of this surfaces in CI.

Eval-Driven Development closes that gap: every change runs through a fixed set of judges before it ships, and the scores it produces survive long enough to compare across iterations.

## The shape

Three primitives:

1. **Headless runner** — invokes the agent without a UI. Same tools, same prompts, no clicking.
2. **Traces** — every run emits structured spans (inputs, tool calls, outputs) into Opik.
3. **Judges** — Opik evaluators score traces on dimensions you care about. Code-based where deterministic, LLM-as-judge where subjective.

Two layers of loop over those primitives:

```
inner loop:  edit → run scenarios → score traces → read table → fix or ship
outer loop:  curate dataset → run experiment → compare on timeline → keep or roll back
```

The inner loop is minutes. The outer loop adds a durable, reviewable artifact: the dataset and the experiments scored against it. Same trace surface, same judges — different shelf life.

## Why not hosted experiment runners alone

Hosted experiment runners (Opik experiments, HRPO-style harnesses, most "eval platforms") replay a dataset against a prompt and score the responses. That's fine when the agent is a single LLM call.

It breaks the moment your agent calls tools. The runner has no toolkit, no auth, no API access — it can only see the prompt-in / response-out shape. Judges that depend on *what the agent did* (did it call the right tool, did it recover from an empty result, did it respect a write-confirmation flow) can't fire, because the trace they'd score never happened.

EDD runs the **real agent harness** end-to-end: real toolkit, real auth, real downstream calls. Traces include every tool invocation. Judges that go beyond response-grading actually have something to grade. The dataset and experiments in the outer loop are built *from* those real traces — the runner is the same harness production traffic flows through.

## What makes it work

**Scenarios are intent-shaped, not exhaustive.** One per behavior you don't want to break: write intent, empty-result recovery, format compliance, terminology adherence. Plain text file, version-controlled, grows with the judge catalog.

**Judges are scoped per run.** Don't fire all judges on every trace — irrelevant ones return neutral scores and drown the signal. Tag scenarios with the dimensions they exercise, only run those.

**0.5 is neutral, not a fail.** The judge abstained. Real failures sit below. The score points at the trace; the trace tells you why.

**Tag every run.** A `run_id` on the agent name plus a `sim-<branch>` tag means you can filter your traces out of a shared project, compare branches side-by-side, and use the same tag to build a dataset from the same batch.

**The dataset is downstream of the sim, not upstream.** You don't hand-write expected outputs. You run scenarios, pick the traces that exercised the surface you care about, snapshot them. The judge scores against the agent's behavior, not against a baked-in answer.

**Optimizations group experiments, not scenarios.** When iterating on a prompt, every experiment lands on the same timeline by sharing an `--optimization-name`. That's the only honest way to claim "v2 is better than v1" — same dataset, same judge, comparable numbers.

## When to skip it

Pure UI changes, refactors that don't touch prompts/tools, bug fixes with a reproducing unit test. Eval is for the surface where types don't reach.

## When raw API tests still matter

If the change touches tool signatures or client shape, run a throwaway script against the live API first. Contract drift fails fast there. Catching it at the judge layer wastes a full run.

Order: raw client → tool wrapper → headless agent → judges → dataset → experiment.

## When to take the outer loop

The inner loop alone is enough for branch-level work. Reach for the dataset + experiment layer when:

- You're iterating on a prompt across days or PRs and need a stable scoreboard
- A reviewer wants to see the number without re-running the sim themselves
- Two prompt variants need to be compared on identical inputs
- The work will eventually feed an HRPO / search-based optimizer that needs a durable target

Otherwise stop at layer 1.

## What you get

The agent's behavior becomes measurable. "Did this change make it better or worse" stops being a vibes question. Model swaps stop being scary. Prompt rot becomes visible — a judge that used to score 0.9 and now scores 0.6 is a signal you didn't have before. The timeline view of an optimization makes that drift obvious to anyone glancing at it.

The point isn't coverage. The point is a feedback loop tight enough that prompt edits feel like code edits, and an artifact stable enough that the score still means something a month from now.
