# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Layout

```
PREREQUISITES.md         ← read first — integration contract + Opik REST caveat
.env.example, .env       ← project config (.env gitignored)
scenarios.example.txt, scenarios.txt    ← per-agent scenarios (.txt gitignored)
regressions.example.txt, regressions.txt ← per-agent baselines (.txt gitignored)
scripts/    ← framework engine (agnostic — pyproject.toml, agent.py, cli.py, ...)
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

All commands run from the **repo root** with the venv active.

### Layer 1 — inner loop (minutes)

```bash
python scripts/cli.py check                              # verify Opik connection
python scripts/cli.py run "Hello agent" --wait           # single message
python scripts/cli.py run scenarios.txt --wait --evaluators "your-evaluator-a,your-evaluator-b"
```

`scenarios.txt`: one scenario per line — plain string or JSON with optional `context`, `followups`, `evaluators` fields.

### Layer 2 — durable dataset + experiment

```bash
# 1. Build dataset from sim traces
python scripts/build_dataset.py \
  --project <opik-project> \
  --dataset-name <project>-<topic>-v1 \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
  --from "$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ)" \
  --dry-run   # preview without writing

# 2. Run experiment
python scripts/run_experiment.py \
  --project <opik-project> \
  --dataset-name <project>-<topic>-v1 \
  --evaluator "your-evaluator-name" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD)

# 3. Inspect results
python scripts/inspect_experiment.py --experiment-name <name-from-previous-step>
```

## Architecture

Two-layer eval loop over three primitives (headless runner, traces, judges):

```
inner loop:  edit → run scenarios → score traces → read table → fix or ship
outer loop:  curate dataset → run experiment → compare on timeline → keep or roll back
```

**Entry point to touch:** `scripts/agent.py` — implement `create_agent()` to return an object with `arun(message) → response.content`. Wire OTEL instrumentor here. The rest of the scripts consume traces via Opik REST.

**Script roles:**

| Script | Role |
|---|---|
| `cli.py` | Layer 1 orchestrator — runs scenarios, tags traces, fires judges, polls scores |
| `agent.py` | **Only file you must edit** — `create_agent` factory + OTEL setup |
| `opik_client.py` | REST wrapper for Opik (traces, datasets, experiments, evaluators) |
| `results.py` | Polls scores and renders per-dimension table |
| `build_dataset.py` | Converts sim traces → Opik dataset (Layer 2) |
| `run_experiment.py` | Runs dataset through judges under an optimization timeline |
| `inspect_experiment.py` | Experiment digest + failure surface |

## Key constraints

- `create_agent` must name the agent starting with `sim-{run_id}-` so traces are filterable by branch tag.
- Don't inject context by concatenating into the user message — mirror how production traffic arrives.
- `--dry-run` before every `build_dataset.py` run to verify the extractor shape.
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
- `references/scenario-design.md` — derive scenario intents from promises; diff-driven agenda
- `references/evaluator-selection.md` — derive dimensions from promises, then pick or build judges
- `references/failure-modes.md` — red judge → likely fix surface (symptom-first, not evaluator-name-first)
- `references/dataset-design.md` — item shape, coverage targets, naming
- `references/experiment-grouping.md` — when to wrap experiments in an optimization
- `references/scoring.md` — how to read the score table
- `references/opik-endpoint-cheatsheet.md` — REST endpoints the scripts use

## Caveat — Opik REST coupling

The framework is tightly coupled to Opik's REST API. Endpoints used by `scripts/opik_client.py` are listed in `references/opik-endpoint-cheatsheet.md`. If a previously-working setup starts erroring after time has passed, suspect API drift first — check Opik release notes before debugging the framework itself.
