---
name: eval_driven_development
description: Eval loop for LLM agents with three modes — (1) quick trace analysis with no UI artifacts, (2) full dataset + experiment in Opik, (3) targeted optimization run against a specific evaluator. Ask the user for mode (1/2/3) and aggression level (1/2/3) before starting. Use after any change to prompts, tools, skills, or model routing.
user-invocable: true
---

# Eval-Driven Development

Three modes, same trace surface:

**Mode 1 — Quick trace analysis.** Simulate scenarios, read trace outputs inline. No Opik UI artifacts, no evaluators fired. Best for fast iteration loops where you want Claude Code to analyze what the agent actually did.

**Mode 2 — Dataset + experiment.** Full inner loop (score traces with judges) then outer loop (build dataset, run experiment, inspect in Opik UI). Best when you need a durable, comparable record across time or people.

**Mode 3 — Optimization run.** Target a single evaluator on a specific prompt change. Runs Opik's optimization studio, freezing the changed section and comparing variants on the same timeline. Best for deliberate prompt engineering with a measurable objective.

Each mode supports three aggression levels — see the **Aggression levels** section.

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

## Start here — ask the user

**Before executing any commands, ask:**

1. **Mode** — which mode do you want to run?
   - `1` — Quick trace analysis (no Opik UI, Claude Code reads traces inline)
   - `2` — Dataset + experiment (full inner + outer loop, results in Opik UI)
   - `3` — Optimization run (targeted prompt change → optimization studio)

2. **Aggression level** — how hard should the scenarios push the agent?
   - `1` — Harness validation: normal user flows, exact trigger phrases, happy paths
   - `2` — Mixed: level 1 + edge cases (empty results, adjacent intents, partial triggers)
   - `3` — Adversarial: mostly edge cases designed to surface harness failures

The mode determines which phase sequence to follow below. The aggression level feeds into scenario generation — apply it when drafting `scenarios.txt` or extending `regressions.txt`.

## Mode 1 — Quick trace analysis

**No Opik UI. No evaluators. Claude Code reads traces directly.**

Use when you want fast signal on what the agent actually did — trace inputs, outputs, tool calls — without the overhead of scoring infrastructure.

1. Generate scenarios at the chosen aggression level (see below) and write to `scenarios.txt`.
2. Run:
   ```bash
   edd run scenarios.txt   # emit + tag, no judging
   ```
3. Fetch and inspect the traces inline:
   ```python
   import sys; sys.path.insert(0, 'scripts')
   from dotenv import load_dotenv; load_dotenv('.env')
   from shared.opik_client import OpikClient
   c = OpikClient()
   traces = c.search_traces(project, from_time='<since>')
   for t in traces:
       print(t['id'][:8], (t.get('input') or {}).get('input.value', '')[:80])
       print(' ->', (t.get('output') or {}).get('output.value', '')[:160])
       meta = t.get('metadata') or {}
       print('  tools:', meta.get('tools_called', []))
   ```
4. Report findings directly in the conversation — what the agent did, what it missed, what looks off. No dataset needed.

**Stop here** unless you need a durable artifact or targeted experiment.

## Setup — Simulate + score (Mode 2, Phase 1)

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

## Simulation — Dataset + experiment (Mode 2, Phase 2)

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

## Mode 3 — Optimization run

**Targeted prompt change → single evaluator → Opik optimization studio.**

Use when you know which dimension is failing and you want to iterate on the fix with a measurable, comparable timeline. The difference from Mode 2: you pick one evaluator to anchor the optimization, make a focused change, and let the studio show the delta.

1. **Identify the dimension** — one failing evaluator, one prompt section to change.
2. **Make the change** in the agent repo (skill file, system prompt section, tool description).
3. **Generate scenarios** focused on that dimension at the chosen aggression level. Write to `scenarios.txt`.
4. **Run the inner loop** to verify the change moves the needle before committing to an experiment:
   ```bash
   edd run scenarios.txt
   python _local/enrich_traces.py --since-minutes 5
   edd score --since 10 --evaluators "<target-evaluator>"
   ```
5. **Build dataset and run experiment** under an optimization name so baseline and post-change land on the same timeline:
   ```bash
   edd-build --project <p> --dataset-name <p>-<topic>-v<N> \
     --branch-tag sim-$(git rev-parse --abbrev-ref HEAD)
   edd-run --project <p> --dataset-name <p>-<topic>-v<N> \
     --evaluator "<target-evaluator>" \
     --branch-tag sim-$(git rev-parse --abbrev-ref HEAD) \
     --optimization-name <topic>-baseline-vs-fix \
     --experiment-name <topic>-post-fix
   ```
6. **Finalize** when the comparison run is the last one:
   ```bash
   edd-run ... --optimization-name <topic>-baseline-vs-fix --finalize-optimization
   ```
7. Inspect the optimization timeline in the Opik UI — score delta is the signal.

## Aggression levels

Apply when generating `scenarios.txt` from the promise inventory (`references/agent-analysis.md`). The level determines how hard scenarios push the agent against its own harness, heuristics, and evaluators.

### Level 1 — Harness validation

Normal user flows. Exact trigger phrases from the skill definitions. Happy paths where data exists and the agent should succeed cleanly. Tests that the core harness works — right skill fires, tools are called, output structure is correct.

*Example for analyze-articles:* "How are my recent articles performing on [publication-url]?"

### Level 2 — Mixed (level 1 + edge cases)

Level 1 scenarios plus: partial trigger phrases, adjacent intents that *might* activate the wrong skill, multi-turn sessions where context shifts mid-way, requests where the tool returns data but the agent might format it incompletely, scenarios where one tool fires but a dependent tool is skipped.

*Example additions:* "What about my writing — what's landing?" (ambiguous trigger), "Which one did best, and what about the format?" (multi-turn, shifts skill mid-session)

### Level 3 — Adversarial

Mostly edge cases designed to surface harness failures. Conflicting instructions, inputs near skill boundaries that might route incorrectly, scenarios where the agent might fabricate (empty result + specific-sounding ask), near-miss out-of-scope asks that test the agent's refusal precision, requests that require multiple dependent tool calls where any one could be skipped.

*Focus:* not "does the happy path work" but "where does the harness break, what does the agent do when data is missing or ambiguous, can the routing be tricked."

Since the goal is to evaluate tool outputs (not just responses), Level 3 scenarios should specifically stress the paths where tool calls might not fire, fire incompletely, or return unexpected shapes.

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

- **Skipping setup.** Going straight to a dataset before the judge fires cleanly on a few traces means you'll find out the judge is broken at experiment scale.
- **Rewriting the dataset in place.** New shape = new version. Comparisons across versions are noise.
- **Running an experiment without an evaluator.** "I want a scoreboard" is not an evaluator — pick the dimension first.
- **Optimization timelines spanning unrelated topics.** Per-topic optimizations keep the UI legible.

## Forking — what lives in `_local/`

The framework core (`scripts/`) is agnostic. Everything specific to your agent
goes in `_local/` at the repo root — gitignored by default. Forkers should create
and version these files themselves (in their fork or working branch):

| File | Purpose |
|---|---|
| `_local/create_evaluators.py` | Create LLM-as-judge rules in your Opik project. Define rubrics from your agent's promise inventory (see `references/agent-analysis.md`). Re-run whenever rubrics change. |
| `_local/enrich_traces.py` | Normalize trace shape for your judges. Walk spans, extract tool names/outputs, patch `metadata.*`. Run between `edd run` and `edd score`. Convention-specific: OpenInference, LangChain, raw OTEL each differ. |
| `_local/openinference_extractor.py` | Custom `--extractor` for `edd-build` if your runtime uses OpenInference trace paths (`input["input.value"]` instead of `input.user_message`). |
| `scenarios.txt` (root) | Diff-specific scenarios for the current session. Regenerated per branch. |
| `regressions.txt` (root) | Stable baseline scenarios covering the agent's core promises. Commit this in your fork — it persists across sessions. |

**Guidance for `_local/` files:**

- `create_evaluators.py`: One judge per promise from your agent's inventory. Use the scoring convention: 1 = explicitly verified correct, 0 = failed OR not applicable (not tested). Document the variable paths your judges use — they depend on your trace shape.
- `enrich_traces.py`: Run after `edd run`, before `edd score`. Keep it thin — extract only what your judges need. If your judges need tool outputs for grounding verification, extract them here.
- **Never commit `_local/` contents to the framework repo.** They encode your agent's specifics. Other users need different rubrics, enrichment, and extractors.

To start fresh with a new agent: copy the `.example.txt` templates, run `references/agent-analysis.md` extraction, then derive `_local/create_evaluators.py` from the promise inventory.
