---
name: eval-driven-development
description: End-to-end eval loop for LLM agents — run scenarios through the real harness, route traces to Opik, score with judges, then optionally build a durable dataset, run experiments under an optimization timeline, and compare iterations. Use after any change to prompts, tools, skills, or model routing.
user-invocable: true
---

# Eval-Driven Development

Two layers of feedback over the same trace surface:

1. **Quick signal** — simulate scenarios, fire judges, read the score table. Minutes.
2. **Durable signal** — distill the sim traces into a dataset, run experiments against it, compare iterations on an optimization timeline. Days to weeks.

Layer 1 is for the inner loop while you tweak. Layer 2 is for the outer loop where iterations need to be comparable across time, people, and prompt versions. They share the trace + judge layer; layer 2 just lifts the same scores into a stable artifact.

For rationale see `README.md`. Mid-loop references:

- `references/scenario-design.md` — branch diff → scenarios + judges to fire
- `references/scoring.md` — reading the score table, judge biases
- `references/failure-modes.md` — red judge → likely fix surface
- `references/evaluator-selection.md` — which judge to anchor a dataset on
- `references/dataset-design.md` — item shape, naming, coverage, versioning
- `references/experiment-grouping.md` — when + how to wrap runs under an Optimization
- `references/opik-endpoint-cheatsheet.md` — REST surface the scripts touch

## When to invoke

After changes to prompts, tool surface, skills, model routing, or memory injection. Skip for pure UI, refactors that don't touch prompts/tools, or bug fixes with a reproducing unit test.

## Setup — Simulate + score

1. **Pick scenarios** that exercise the surfaces the diff touches — one per intent. Keep under 10 for fast feedback.
2. **Pick judges** that should have an opinion. Skip irrelevant ones — they drown signal with neutral 0.5 scores.
3. **Run**. Two paths depending on whether your traces need enrichment before scoring:

   *No enrichment needed (simple agents):*
   ```bash
   edd run scenarios.txt --wait --evaluators "<names>"
   ```

   *With enrichment (e.g. OpenInference — add tool-call metadata before judges fire):*
   ```bash
   edd run scenarios.txt                            # emit + tag, exit
   python _local/enrich_traces.py --since-minutes 5 # your enrichment step
   edd score --since 10                             # trigger judges + poll + print table
   ```
   The CLI tags every trace `sim-<branch>` — that tag is the join key for simulation.

4. **Read the table** — below 0.5 = real failure. Red cells print the judge's reason inline. See `references/scoring.md`.
5. **Open the trace** for any failure. Cross-reference `references/failure-modes.md`.
6. **Fix and re-run** until green.

This loop is enough for most branch-level work.

## Simulation — Dataset + experiment

Use when you want the score to outlive the branch:

- comparing two prompt variants on the same inputs
- iterating across days and needing a timeline view of progress
- producing a baseline a later HRPO / optimizer loop will run against
- handing the score off to a reviewer who wasn't in the inner loop

### Phase A — Pick the evaluator

Consult `references/evaluator-selection.md`. The chosen evaluator's schema name flows through every later command — pin it before designing the dataset.

### Phase B — Design the dataset

Consult `references/dataset-design.md`. Decide naming (`<project>-<topic>-<version>`), coverage mix, and whether you need metadata propagated through the trace.

### Phase C — Tag a sim batch

Setup already tags traces `sim-<branch>`. If you need fresh ones for the dataset, run the full setup loop from Step 3 (with or without enrichment). Don't skip enrichment here — judges in the experiment will read the same variable paths they used in setup.

### Phase D — Build the dataset

```bash
edd-build \
  --project <opik-project> \
  --dataset-name <project>-<topic>-v1 \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
  --from "$(date -u -v-6H +%Y-%m-%dT%H:%M:%SZ)" \
  [--extractor my_pkg.extractors:my_fn] \
  [--dry-run]
```

`--dry-run` first — it prints the planned items without writing. The default extractor reads `user_message` + `assistant_response`; supply `--extractor module:function` for runtimes that shape traces differently.

### Phase E — Run the experiment

```bash
edd-run \
  --project <opik-project> \
  --dataset-name <project>-<topic>-v1 \
  --evaluator "<name-a>,<name-b>,<name-c>" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
  [--optimization-name <topic>-baseline-vs-v2] \
  [--score-timeout 300] \
  [--dry-run]
```

Triggers the evaluator on every linked trace, polls scores, creates the experiment with model + branch + evaluator metadata, copies scores onto experiment items. Wrapping under `--optimization-name` puts the run on a comparable timeline (`references/experiment-grouping.md`).

### Phase F — Inspect + iterate

```bash
edd-inspect \
  --experiment-id <uuid> \
  [--score-threshold 0.5] \
  [--evaluator "<Schema Name>"] \
  [--out-jsonl /tmp/exp.jsonl]
```

Prints a per-evaluator digest + failures below threshold with trace links. Use `references/failure-modes.md` to classify:

- **prompt issue** → fix prompt/skill/tool, re-run from Phase E (same dataset, same optimization → new experiment shows up on the timeline)
- **dataset issue** → patch scenarios, rebuild dataset (Phase D), new version
- **evaluator issue** → recalibrate judge, re-run from Phase E
- **flaky / model-bound** → tag and skip

Two *prompt iterations* on the same red judge = stop tweaking the prompt, widen the search. See `references/failure-modes.md` for the distinction between prompt iterations and re-runs of the same trace (judge noise).

## Files

| Path | Command | Purpose |
|------|---------|---------|
| `scripts/setup/cli.py` | `edd` | Setup orchestrator — run scenarios, tag traces, trigger judges, poll scores |
| `scripts/setup/agent.py` | — | **Wire your runtime here** — `create_agent` factory + OTEL |
| `scripts/setup/results.py` | — | Polls scores, renders the per-dimension table with inline reasons |
| `scripts/shared/opik_client.py` | — | REST wrapper (traces, datasets, experiments, optimizations, evaluators) |
| `scripts/simulation/build_dataset.py` | `edd-build` | Simulation — sim traces → Opik dataset |
| `scripts/simulation/run_experiment.py` | `edd-run` | Simulation — dataset → experiment (optional optimization grouping) |
| `scripts/simulation/inspect_experiment.py` | `edd-inspect` | Simulation — experiment digest + failure surface |
| `scripts/pyproject.toml` | — | Dependencies + entry points |
| `scenarios.example.txt` | — | Sample scenarios (root — copy to `scenarios.txt`, gitignored) |
| `regressions.example.txt` | — | Baseline scenarios (root — copy to `regressions.txt`, gitignored) |
| `.env.example` | — | Required env vars (root) |
| `PREREQUISITES.md` | — | **Read first** — integration contract + Opik REST coupling caveat |
| `references/agent-analysis.md` | — | Extract promise inventory from agent source |
| `references/trace-inspection.md` | — | Inspect trace shape + write enrichment if judges need normalization |
| `references/scenario-design.md` | — | Promise → scenario intent → instances (setup) |
| `references/evaluator-selection.md` | — | Derive dimensions from promises, then pick / build judges |
| `references/failure-modes.md` | — | Red judge → likely fix surface (symptom-first) |
| `references/scoring.md` | — | Reading the score table |
| `references/dataset-design.md` | — | Item shape, naming, coverage (simulation) |
| `references/experiment-grouping.md` | — | Optimization timelines (simulation) |
| `references/opik-endpoint-cheatsheet.md` | — | REST surface the scripts touch |
| `README.md` | — | Rationale |

## Prerequisites

- An **Opik instance** with a **dedicated testing project** (not production)
- Judges defined in that project with `enabled=False, sampling_rate=0` (manual-trigger mode — see `references/evaluator-selection.md` Step 4)
- Scenario file (setup) or a recipe that produces tagged sim traces (simulation)

## Quickstart

```bash
cd scripts && pip install -e . && cd ..
cp .env.example .env  # OPIK_URL, OPIK_API_KEY, OPIK_OTLP_ENDPOINT

# wire create_agent in scripts/setup/agent.py, then run from root:
edd check
edd run "Hello agent" --wait

# simulation (when you want a durable score):
edd-build --project <p> --dataset-name <p>-<topic>-v1 \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) --dry-run
edd-run --project <p> --dataset-name <p>-<topic>-v1 \
  --evaluator "<your-evaluator-name>" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD)
edd-inspect --experiment-name <name-from-previous-step>
```

## Anti-patterns

- **Skipping layer 1.** Going straight to a dataset before the judge fires cleanly on a few traces means you'll find out the judge is broken at experiment scale.
- **Rewriting the dataset in place.** New shape = new version. Comparisons across versions are noise.
- **Running an experiment without an evaluator.** "I want a scoreboard" is not an evaluator — pick the dimension first.
- **Optimization timelines spanning unrelated topics.** Per-topic optimizations keep the UI legible.
