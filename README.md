# Eval-Driven Development for LLM Agents

Tests tell you code runs. They don't tell you the agent is still good at its job.

A prompt edit that fixes one behavior breaks three others silently. A model swap shifts response shape. Tool routing drifts after a schema change. None of this surfaces in CI — and most eval platforms can't catch it either, because they replay inputs against a prompt without running the real toolkit.

EDD closes the gap: run the live agent against real scenarios, capture every tool call, score with judges that see what the agent actually did.

---

## How it works

Three primitives — headless runner, traces, judges — composed into two loops.

```
inner loop  (minutes):  run scenarios → score traces → read table → fix or ship
outer loop  (hours+):   curate dataset → run experiment → compare on timeline → keep or roll back
```

The runner invokes the agent over HTTP. The agent emits traces to Opik directly. EDD reads those traces via REST, tags them, enriches metadata, and fires judges against exactly the traces it just ran — not auto-sampled noise from the rest of the project.

### Architecture

```
scenarios.txt
      │
      ▼
  edd run ─── HTTP ───▶  Agent under test
      │                  (real tools · real auth · real data)
      │                         │
      │                    OTEL / SDK
      │                         │
      └──── REST (tag) ───▶  Opik
                               │  traces land with every tool call recorded
                               │
           enrich_traces.py ◀──┘   normalise metadata per SDK
                               │
           edd score ──────────┘   fire judges · poll scores · print table
                               │
           edd-build ──────────┘   traces → dataset
                               │
           edd-run  ───────────┘   dataset → experiment
                               │
           edd-inspect ────────┘   digest · failures · trace links
```

---

## Three modes

Choose based on how much signal you need.

### Mode 1 — Quick trace analysis (minutes)

No Opik UI. No evaluators. Fast feedback on what the agent actually did.

```
scenarios.txt ──▶ edd run ──▶ read traces inline ──▶ fix or ship
```

Use for: rapid iteration, validating a single prompt change, debugging routing.

### Mode 2 — Dataset + experiment (hours)

Full inner loop then outer loop. Produces a durable, comparable record in Opik.

```
edd run ──▶ enrich ──▶ edd score ──▶ score table
                                          │
                                     edd-build      traces → dataset
                                          │
                                      edd-run        dataset → experiment
                                          │
                                    edd-inspect      delta view in Opik UI
```

Use for: comparing two prompt versions, producing a baseline, sharing results with someone who wasn't in the inner loop.

### Mode 3 — Optimization run (days)

Multiple Mode 2 experiments grouped under one Opik optimization timeline. Each iteration adds a data point to the same scoreboard.

```
experiment v1 ─┐
experiment v2 ─┼──▶  Opik optimization timeline  ──▶  delta speaks for itself
experiment vN ─┘
```

Use for: iterating on a specific dimension across several prompt versions, validating a hypothesis with a before/after comparison.

---

## Why not a hosted eval runner?

Hosted runners (Opik experiments, HRPO harnesses, most eval platforms) replay a dataset against a prompt and score the responses. That works when the agent is a single LLM call.

It breaks the moment your agent calls tools. The runner has no toolkit, no auth, no API access — judges that depend on what the agent *did* (right tool called, empty result handled, scope respected) can't fire, because the trace they'd score never happened.

EDD runs the **real agent harness** end-to-end. The dataset and experiments in the outer loop are built from those real traces — the runner is the same harness production traffic flows through.

---

## Setup

```bash
cd scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cd ..
cp .env.example .env   # fill in OPIK_URL, OPIK_API_KEY, AGENT_ENDPOINT
edd check              # verify connectivity
```

**Requirements:**
- Agent reachable over HTTP — `POST {AGENT_ENDPOINT}` with `{"message", "session_id"}` → `{"content"}`
- Agent emits traces to Opik (OTEL exporter or Opik SDK — the framework doesn't instrument the agent)
- Opik project with judges defined (`enabled=False, sampling_rate=0` for manual-trigger mode)

---

## Project layout

```
scripts/
  setup/        cli.py (edd), agent.py, results.py
  simulation/   build_dataset.py (edd-build), run_experiment.py (edd-run), inspect_experiment.py (edd-inspect)
  shared/       opik_client.py, settings.py
references/     decision guides (agent-analysis, evaluator-selection, trace-inspection, ...)
_local/         per-agent: evaluators, enrichment, extractors  ← gitignored, yours to define
```

Runtime-specific code (trace enrichment, custom HTTP adapter, dataset extractor) lives in `_local/` — gitignored, per-fork. The framework core is agnostic.

---

## Design principles

**Judges from promises, not from a taxonomy.** Read the agent source. For each behavioral promise, derive one dimension. Name it from the failure mode. One sentence for pass, one for fail.

**Trajectory context is not optional.** Grounding judges need to know which tools fired — not just the response. Without tool call context, grounding and hallucination are indistinguishable.

**Manual-trigger mode during development.** Auto-sampling mixes sim traffic with exploratory dev runs and drowns the signal. Fire judges only on the traces you just ran.

**The dataset is downstream of the sim.** You don't hand-write expected outputs. You run scenarios, pick the traces that exercised the surface you care about, snapshot them. The judge scores against the agent's actual behavior.

---

## When to skip it

Pure UI changes, refactors that don't touch prompts or tools, bug fixes with a reproducing unit test. EDD is for the surface where types don't reach.

---

## Resources

- [skills/run/SKILL.md](skills/run/SKILL.md) — invoke as `/eval-driven-development:run` in Claude Code (install plugin with `--plugin-dir`)
- [PREREQUISITES.md](PREREQUISITES.md) — integration contract + adapter pattern
- [references/](references/) — agent analysis, evaluator selection, trace inspection, scenario design
