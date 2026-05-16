---
name: eval-driven-development
description: Eval loop for LLM agents with three modes — (1) quick trace analysis with no UI artifacts, (2) full dataset + experiment in Opik, (3) targeted optimization run against a specific evaluator. Ask the user for mode (1/2/3) and aggression level (1/2/3) before starting. Use after any change to prompts, tools, skills, or model routing.
user-invocable: true
---

# Eval-Driven Development

Three modes, same trace surface:

**Mode 1 — Quick trace analysis.** Simulate scenarios, read trace outputs inline. No Opik UI artifacts, no evaluators fired. Best for fast iteration loops where you want Claude Code to analyze what the agent actually did.

**Mode 2 — Dataset + experiment.** Full inner loop (score traces with judges) then outer loop (build dataset, run experiment, inspect in Opik UI). Best when you need a durable, comparable record across time or people.

**Mode 3 — Optimization run.** Target a single evaluator on a specific prompt change. Runs Opik's optimization studio, freezing the changed section and comparing variants on the same timeline. Best for deliberate prompt engineering with a measurable objective.

Each mode supports three aggression levels (1 = harness, 2 = mixed, 3 = adversarial) — see `references/scenario-design.md`.

## References — when to load each

**Before first run** (read once when setting up a new agent):
- `PREREQUISITES.md` — integration contract; Opik REST caveat; judge model workspace dep
- `references/agent-analysis.md` — extract promise inventory from agent source
- `references/trace-inspection.md` — find your trace shape; design enrichment for `_local/`
- `references/evaluator-selection.md` — dimensions from promises → judges; scoring convention
- `references/scenario-design.md` — scenario intents from promises; aggression levels

**During setup loop** (open when reading scores or diagnosing a failure):
- `references/scoring.md` — score table thresholds; judge biases; non-determinism rules
- `references/failure-modes.md` — red judge → likely fix surface (symptom-first)

**During simulation / optimization** (open when building datasets or experiments):
- `references/dataset-design.md` — item shape, extractor pattern, coverage, naming
- `references/experiment-grouping.md` — when and how to wrap runs under an Optimization

**If the REST layer breaks** (open when scripts error on Opik endpoints):
- `references/opik-endpoint-cheatsheet.md` — all endpoint shapes the scripts use

**Rationale** (open if someone asks why this approach):
- `README.md`

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
   from shared.opik_client import OpikClient
   c = OpikClient()
   traces = c.search_traces(project, from_time='<since>')
   for t in traces:
       inp = t.get('input') or {}
       out = t.get('output') or {}
       meta = t.get('metadata') or {}
       # Input/output paths vary by SDK — read references/trace-inspection.md for your convention:
       # Agno/OpenInference:  inp.get('input.value'), out.get('output.value')
       # Anthropic SDK:       inp.get('message'), out.get('output')
       # OpenAI Agents SDK:   inp.get('input',[{}])[0].get('content'), extract from out.get('output',[])
       # After enrichment, all SDKs: meta.get('user_message'), meta.get('assistant_response')
       print(t['id'][:8], str(inp)[:80])
       print(' ->', str(out)[:160])
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

   *With enrichment (your runtime needs trace normalization before judges fire):*
   ```bash
   edd run scenarios.txt                                         # emit + tag, exit
   python _local/enrich_traces_<sdk>.py --since-minutes 5       # SDK-specific enrichment
   edd score --since 10                                          # trigger judges + poll + print table
   ```
   Use the enrichment script matching your SDK (`enrich_traces.py` for Agno, `enrich_traces_claude.py` for Anthropic SDK, `enrich_traces_openai.py` for OpenAI Agents SDK). The CLI tags every trace `sim-<branch>` — that tag is the join key for simulation.

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

Two paths — choose based on whether your agent is a direct LLM call or an HTTP service:

### 3A — Manual comparison (any HTTP agent)

Target one failing dimension, make a focused change, compare baseline vs. post-fix on a shared Opik optimization timeline. Works for any agent type.

1. Identify the dimension and the prompt section to change (skill file, system prompt, tool description).
2. Make the change in the agent repo.
3. Run inner loop focused on that dimension:
   ```bash
   edd run scenarios.txt
   python _local/enrich_traces_<sdk>.py --since-minutes 5
   edd score --since 10 --evaluators "<target-evaluator>"
   ```
4. Build dataset and run experiment under a shared optimization name:
   ```bash
   edd-build --project <p> --dataset-name <p>-<topic>-v<N> \
     --branch-tag sim-$(git rev-parse --abbrev-ref HEAD)
   edd-run --project <p> --dataset-name <p>-<topic>-v<N> \
     --evaluator "<target-evaluator>" \
     --optimization-name <topic>-baseline-vs-fix \
     --experiment-name <topic>-post-fix
   ```
5. Finalize and inspect the timeline delta:
   ```bash
   edd-run ... --finalize-optimization
   edd-inspect --experiment-name <topic>-post-fix
   ```

### 3B — Studio optimization (direct-LLM prompts only)

Uses `opik_optimizer.MetaPromptOptimizer` to automatically generate improved prompt variants and score them with a custom metric. Works when the prompt drives a direct LLM call — **not** when the agent is a multi-skill HTTP service (Agno, etc.) without a custom `OptimizableAgent` wrapper.

```bash
pip install opik-optimizer   # not in core deps
python _local/run_optimization.py --trials 3 --samples 5
```

`_local/run_optimization.py` — per-agent script (gitignored):
- `prompt`: the skill instructions or system prompt section to optimize
- `metric`: a function `(dataset_item, llm_output) -> float` scoring the output
- `dataset`: an Opik dataset with `{user_message}` field per item
- `optimize_prompts="system"` — only the system prompt is mutated; user template is fixed

**Limitation for HTTP agents:** The optimizer calls the LLM directly, bypassing your agent's runtime. If your agent loads skills dynamically (like Agno), the optimizer's baseline may be 1.0 even when the real agent scores 0 — the skill instructions are correct, but the agent's skill loader applies them differently. In that case, use 3A (manual comparison) and investigate the runtime layer.

## Files

| Path | Command | Purpose |
|------|---------|---------|
| `scripts/setup/agent.py` | — | Generic HTTP adapter — do not edit. Set `AGENT_ADAPTER=_local.my_adapter:create_agent` in `.env` to override for non-standard contracts. |
| `scripts/setup/cli.py` | `edd` | Orchestrator — emit scenarios, tag traces, trigger judges, poll scores |
| `scripts/setup/results.py` | — | Score table renderer with inline judge reasons |
| `scripts/shared/opik_client.py` | — | Opik REST wrapper (traces, datasets, experiments, evaluators) |
| `scripts/simulation/build_dataset.py` | `edd-build` | Sim traces → Opik dataset |
| `scripts/simulation/run_experiment.py` | `edd-run` | Dataset → experiment (optional optimization grouping) |
| `scripts/simulation/inspect_experiment.py` | `edd-inspect` | Experiment digest + failure surface |
| `scenarios.example.txt` | — | Copy to `scenarios.txt` (gitignored) |
| `regressions.example.txt` | — | Copy to `regressions.txt` (gitignored) |
| `.env.example` | — | Required env vars |

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
| `_local/enrich_traces_<sdk>.py` | Normalize trace shape for your judges. Walk spans, extract `user_message`, `assistant_response`, `tools_called`, `tool_outputs`, patch `metadata.*`. Run between `edd run` and `edd score`. Write one per SDK when multiple SDKs share an Opik project — each script must discriminate its own traces and skip the rest. See `references/trace-inspection.md`. |
| `_local/<runtime>_extractor.py` | Custom `--extractor` for `edd-build` when your runtime emits trace paths that differ from defaults. One function returning `{user_message, assistant_response}` per trace, importable from repo root. |
| `_local/my_adapter.py` | **Optional.** Custom HTTP adapter when your agent's contract differs from the generic default (`{"message", "session_id"}` → `{"content"}`). Set `AGENT_ADAPTER=_local.my_adapter:create_agent` in `.env`. Leave unset for standard REST agents. See `PREREQUISITES.md`. |
| `scenarios.txt` (root) | Diff-specific scenarios for the current session. Regenerated per branch. |
| `regressions.txt` (root) | Stable baseline scenarios covering the agent's core promises. Commit this in your fork — it persists across sessions. |

**Two places for runtime-specific code — different purposes:**

`scripts/setup/agent.py` is the **framework core — do not edit it**. It loads `AGENT_ADAPTER` from `.env` if set; otherwise uses the generic JSON default. Runtime-specific fields (different body shape, field names, auth, timeout) go in `_local/my_adapter.py` and are referenced via the env var.

`_local/` is **gitignored scratchpad** for per-agent configuration that shouldn't be in the framework repo at all — rubrics, enrichment scripts, extractors. Never commit `_local/` to the framework remote; it encodes your agent's specifics and would break other users' setups.

**Guidance for `_local/` files:**

- `create_evaluators.py`: One judge per promise from your agent's inventory. Use the scoring convention: 1 = explicitly verified correct, 0 = failed OR not applicable (not tested). Document the variable paths your judges use — they depend on your trace shape.
- `enrich_traces_<sdk>.py`: Run after `edd run`, before `edd score`. Each script must (1) skip traces it doesn't own (SDK discriminator check on trace input keys or metadata), (2) write `user_message` + `assistant_response` + `tools_called` + `tool_outputs` to `metadata.*`. Evaluators read only from `metadata.*` — they never touch native SDK trace paths. See `references/trace-inspection.md` for extraction patterns per SDK.
- `my_adapter.py`: Only needed when the agent's HTTP contract differs from the generic default. Implement `create_agent(session_id, run_id, context)` returning an object with `arun(message) → SimpleNamespace(content=...)`. See `PREREQUISITES.md` for the full interface and examples.
- `<runtime>_extractor.py`: One function returning a dict per trace, importable from repo root. Pass via `--extractor` to `edd-build`.

To start fresh with a new agent: copy the `.example.txt` templates, run `references/agent-analysis.md` extraction, then derive `_local/create_evaluators.py` from the promise inventory.
