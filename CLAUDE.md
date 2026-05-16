# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout

```
PREREQUISITES.md         ← read first — integration contract + Opik REST caveat
.env.example, .env       ← project config (.env gitignored)
scenarios.example.txt, scenarios.txt    ← per-agent scenarios (.txt gitignored)
regressions.example.txt, regressions.txt ← per-agent baselines (.txt gitignored)
scripts/                 ← framework engine
  setup/                   ← setup phase: run scenarios, tag traces, score (edd)
  simulation/              ← simulation phase: dataset, experiment, inspect (edd-build / edd-run / edd-inspect)
  shared/                  ← REST wrapper (opik_client.py)
  pyproject.toml
references/ ← decision guides
```

## Setup

```bash
cd scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cd ..
cp .env.example .env   # fill in OPIK_URL, OPIK_API_KEY, OPIK_OTLP_ENDPOINT
```

Required env vars: `OPIK_URL`, `OPIK_API_KEY`, `OPIK_OTLP_ENDPOINT` (Opik instance), and `AGENT_ENDPOINT` (HTTP URL of the agent under test). See `PREREQUISITES.md` for the full integration contract.

## Commands

All commands run from the **repo root** with the venv active (`source scripts/.venv/bin/activate`).

### Setup — inner loop (minutes)

```bash
edd check                                   # verify Opik connection

# No enrichment needed (simple agents):
edd run "Hello agent" --wait                # single message — emit + score in one shot
edd run scenarios.txt --wait --evaluators "your-evaluator-a,your-evaluator-b"

# With enrichment (runtime needs trace-shape normalization before scoring):
edd run scenarios.txt                       # emit + tag only (no judges)
python _local/enrich_traces.py --since-minutes 5
edd score --since 10                        # trigger judges on last N minutes of traces
```

`scenarios.txt`: one scenario per line — plain string or JSON with optional `context`, `followups`, `evaluators` fields.

### Simulation — durable dataset + experiment

```bash
# 1. Build dataset from sim traces
edd-build \
  --project <opik-project> \
  --dataset-name <project>-<topic>-v1 \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
  --from "$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ)" \
  --dry-run   # preview without writing

# 2. Run experiment
edd-run \
  --project <opik-project> \
  --dataset-name <project>-<topic>-v1 \
  --evaluator "your-evaluator-a,your-evaluator-b" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD)

# 3. Inspect results
edd-inspect --experiment-name <name-from-previous-step>
```

## Architecture

Two-phase eval loop over three primitives (headless runner, traces, judges):

```
setup:       edit → run scenarios → score traces → read table → fix or ship
simulation:  curate dataset → run experiment → compare on timeline → keep or roll back
```

**Entry point to touch:** `scripts/setup/agent.py` — implement `create_agent()` to return an object with `arun(message) → response.content`. Wire OTEL instrumentor here. The rest of the scripts consume traces via Opik REST.

**Module roles:**

| Module | Command | Role |
|---|---|---|
| `setup/cli.py` | `edd` | Orchestrator — run scenarios, tag traces, trigger judges, poll scores |
| `setup/agent.py` | — | **Only file you must edit** — `create_agent` factory + OTEL setup |
| `setup/results.py` | — | Renders per-dimension score table with inline judge reasoning |
| `shared/opik_client.py` | — | REST wrapper for Opik (traces, datasets, experiments, evaluators) |
| `simulation/build_dataset.py` | `edd-build` | Converts sim traces → Opik dataset |
| `simulation/run_experiment.py` | `edd-run` | Runs dataset through judges under an optimization timeline |
| `simulation/inspect_experiment.py` | `edd-inspect` | Experiment digest + failure surface |

## Key constraints

- `create_agent` must name the agent starting with `sim-{run_id}-` so traces are filterable by branch tag.
- Don't inject context by concatenating into the user message — mirror how production traffic arrives.
- `--dry-run` before every `edd-build` run to verify the extractor shape.
- Supply `--extractor module:function` when trace shape differs from defaults (`trace.input.user_message` / `trace.output.assistant_response`).
- Dataset naming convention: `<project>-<topic>-v<N>`. Pin `dataset_version_id` per experiment; bump the name to start a new optimization timeline.

## Per-agent artifacts (gitignored at framework level)

`scenarios.txt` and `regressions.txt` (root) are gitignored — they're per-agent, not framework files. The framework ships `*.example.txt` templates only.

Workflow on a fresh agent:

1. Run `references/agent-analysis.md` extraction → produce a promise inventory.
2. Copy `regressions.example.txt` → `regressions.txt`. Populate with 5–8 baseline scenarios (one per core promise). **Commit this in your fork / working branch** — it persists across sessions.
3. Copy `scenarios.example.txt` → `scenarios.txt`. Generate diff-specific scenarios per session.

**Always check for an existing `regressions.txt` before re-deriving baselines.** If it's present, read it first — running fresh agent-analysis every session wastes tokens and drifts the baseline.

## Reference docs

Read in this order:

- `PREREQUISITES.md` (root) — **read first** — integration contract (agent over HTTP, agent traces to Opik directly, Opik REST coupling caveat)
- `references/agent-analysis.md` — extract promise inventory from any agent source
- `references/trace-inspection.md` — inspect your trace shape, write enrichment if your judges need normalization
- `references/evaluator-selection.md` — derive dimensions from promises, then pick or build judges; **drives scenario design and dataset shape**
- `references/scenario-design.md` — derive scenario intents from promises; tag each with the judge names from evaluator-selection
- `references/scoring.md` — how to read the score table
- `references/failure-modes.md` — red judge → likely fix surface (symptom-first, not evaluator-name-first)
- `references/dataset-design.md` — item shape, coverage targets, naming; anchored to the evaluator from evaluator-selection
- `references/experiment-grouping.md` — when to wrap experiments in an optimization
- `references/opik-endpoint-cheatsheet.md` — REST endpoints the scripts use

## Caveat — Opik REST coupling

The framework is tightly coupled to Opik's REST API. Endpoints used by `scripts/shared/opik_client.py` are listed in `references/opik-endpoint-cheatsheet.md`. If a previously-working setup starts erroring after time has passed, suspect API drift first — check Opik release notes before debugging the framework itself.
