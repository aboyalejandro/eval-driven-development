# Eval-Driven Development for LLM Agents

> ⚠️ **Active development.** This framework is under active iteration — APIs, skill bodies, and CLI flags will change without notice. **No remote/registry install yet.** Install locally as a Claude Code plugin from a cloned copy of this repo — see [`DEVELOPMENT.md`](DEVELOPMENT.md). Pin to a commit if you need stability.

Tests tell you code runs. They don't tell you the agent is still good at its job.

A prompt edit that fixes one behavior breaks three others silently. A model swap shifts response shape. Tool routing drifts after a schema change. None of this surfaces in CI — and most eval platforms can't catch it either, because they replay inputs against a prompt without running the real toolkit.

EDD closes the gap: run the live agent against real scenarios, capture every tool call, score with judges that see what the agent actually did.

## How it works

Three primitives — headless runner, traces, judges — composed into two loops.

```
inner loop  (minutes):  run scenarios → score traces → read table → fix or ship
outer loop  (hours+):   curate dataset → run experiment → compare on timeline → keep or roll back
```

The runner invokes the agent over HTTP. The agent emits traces to Opik directly. EDD reads those traces via REST, tags them, enriches metadata, and fires judges against exactly the traces it just ran — not auto-sampled noise from the rest of the project.

## Why not a hosted eval runner?

Hosted runners (Opik experiments, HRPO harnesses, most eval platforms) replay a dataset against a prompt and score the responses. That works when the agent is a single LLM call.

It breaks the moment your agent calls tools. The runner has no toolkit, no auth, no API access — judges that depend on what the agent *did* (right tool called, empty result handled, scope respected) can't fire, because the trace they'd score never happened.

EDD runs the **real agent harness** end-to-end. The dataset and experiments in the outer loop are built from those real traces — the runner is the same harness production traffic flows through.

## When to skip it

Pure UI changes, refactors that don't touch prompts or tools, bug fixes with a reproducing unit test. EDD is for the surface where types don't reach.

## Resources

- [DEVELOPMENT.md](DEVELOPMENT.md) — local install: register the plugin, install the CLI, wire env vars, troubleshoot.
- [CLAUDE.md](CLAUDE.md) — repo sitemap (skills, scripts modules, references) + key constraints.
- [skills/CLAUDE.md](skills/CLAUDE.md) — sub-skill index, pipeline DAG, cross-cutting rules.
- [references/CLAUDE.md](references/CLAUDE.md) — decision guides, "load when X" index.
- [PREREQUISITES.md](PREREQUISITES.md) — integration contract + adapter pattern.
