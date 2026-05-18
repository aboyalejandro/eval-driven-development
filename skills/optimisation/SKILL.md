---
name: optimisation
description: Iterative prompt fix on one judge — baseline vs post-fix on a shared Opik optimization timeline. Use after `edd:run` / `edd:experiment` has surfaced a persistent failure on a single dimension. Two paths — 3A manual comparison (any HTTP agent) or 3B studio via `opik_optimizer.MetaPromptOptimizer` (direct-LLM prompts only). Invoke as `edd:optimisation` or when the user says "optimize the prompt", "iterate on this judge", "edd mode 3". For *building the durable scoreboard*, see `edd:experiment`.
---

# edd:optimisation — targeted prompt optimization

Mode 3 of the eval pipeline. Single evaluator, single prompt section, measurable delta on an Opik optimization timeline.

> The Opik `Optimization` entity is a generic timeline-grouping primitive — manual variant comparison (3A) and `opik_optimizer.MetaPromptOptimizer` (3B) write to the same entity. The HRPO/MIPRO loop is one valid producer; manual `--optimization-name` runs are another.

## Preconditions

- `.edd/session.json` has `project`, `branch_tag`, `topic`
- One target evaluator picked — should be the dimension that's persistently red across [`edd:run`](../run/SKILL.md) or [`edd:experiment`](../experiment/SKILL.md)
- Identified prompt section to mutate (skill file, system prompt block, tool description)
- venv active

## Branch — pick 3A or 3B

| Agent shape | Path |
|---|---|
| HTTP service (Agno, multi-skill router, anything with a skill loader) | **3A — Manual comparison** |
| Direct LLM call (single prompt → completion, no runtime skill loader) | **3B — Studio optimization** |

**If unsure, use 3A.** 3B has a sharp limitation for HTTP agents — see warning at bottom.

---

## 3A — Manual comparison (any HTTP agent)

Baseline run already exists (from prior [`edd:experiment`](../experiment/SKILL.md)). Mutate the prompt, re-run, compare on a shared optimization timeline.

### Step 1 — Pin baseline

Confirm a baseline experiment exists under an `--optimization-name`. If not, run [`edd:experiment`](../experiment/SKILL.md) first with `--optimization-name <topic>-baseline-vs-fix` so the post-fix run lands on the same timeline.

### Step 2 — Change the prompt

One focused change in the agent repo — the prompt section that the target evaluator scores. Don't co-mutate other surfaces; you lose attribution.

### Step 3 — Inner loop on target evaluator

```bash
edd run scenarios.txt
python _local/enrich_traces_<sdk>.py --since-minutes 5
edd score --since 10 --evaluators "<target-evaluator>"
```

Verify the change moved the needle on a few scenarios before committing to a full experiment.

### Step 4 — Post-fix experiment under shared optimization

```bash
edd-build \
  --project <project> \
  --dataset-name <project>-<topic>-v<N> \
  --description "<dataset summary>" \
  --branch-tag sim-$(git rev-parse --abbrev-ref HEAD)

edd-run \
  --project <project> \
  --dataset-name <project>-<topic>-v<N> \
  --evaluator "<target-evaluator>" \
  --description "post-fix variant — <what you changed>" \
  --optimization-name <topic>-baseline-vs-fix \
  --optimization-description "<reused on first upsert of the optimization>" \
  --experiment-name <topic>-post-fix
```

Both `--description` flags are required by their respective CLIs. `--optimization-description` lands once (on the first upsert of the optimization) and is reused for subsequent variants on the same timeline.

Same dataset, same evaluator, same optimization → post-fix appears as a new point on the timeline alongside baseline.

### Step 5 — Finalize + inspect delta

```bash
edd-run ... --finalize-optimization
edd-inspect --experiment-name <topic>-post-fix
```

`--finalize-optimization` closes the optimization (no further runs land on it). Skip if you plan more variants on the same timeline.

Compare baseline vs post-fix in the Opik optimization UI. Decision rule per [stopping rules](../CLAUDE.md#stopping-rules): keep iff post-fix beats baseline by ≥ 0.1 with no regression elsewhere.

---

## 3B — Studio optimization (direct-LLM prompts only)

Uses `opik_optimizer.MetaPromptOptimizer` to automatically generate improved prompt variants and score them with a custom metric.

### Install

```bash
pip install opik-optimizer   # not in core deps
```

### Step 1 — Write `_local/run_optimization.py`

```python
from opik_optimizer import MetaPromptOptimizer
from opik import Opik

opik = Opik()
dataset = opik.get_dataset("<project>-<topic>-v<N>")

def metric(dataset_item, llm_output) -> float:
    # 1.0 if llm_output satisfies the target promise, else 0.0
    ...

optimizer = MetaPromptOptimizer(
    prompt="<the skill instructions or system prompt section to optimize>",
    metric=metric,
    dataset=dataset,
    optimize_prompts="system",   # only the system prompt mutates
    model="anthropic/claude-sonnet-4-6",
)

result = optimizer.optimize(trials=3, samples=5)
print(result)
```

### Step 2 — Run

```bash
python _local/run_optimization.py --trials 3 --samples 5
```

The optimizer generates variants, scores each via `metric`, and posts the trial timeline to the Opik optimization studio.

### Limitation — read this before using 3B

The optimizer calls the LLM **directly**, bypassing your agent's runtime. If your agent loads skills dynamically (Agno) or has a tool-calling loop, the optimizer's baseline may score 1.0 even when the real agent scores 0 — the skill instructions are correct in isolation but the runtime applies them differently.

**Symptom:** optimizer baseline ≫ inner-loop baseline on the same scenarios.
**Fix:** abandon 3B, fall back to 3A, investigate the runtime layer.

---

## Anti-patterns

- Running 3B on an HTTP agent without verifying baseline parity with the real runtime.
- Skipping the inner loop pre-check — if `edd:run` doesn't show the change moved the needle on 3–5 scenarios, the full experiment will waste compute.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global, including co-mutating prompt sections and optimization-name span).

## Next

- Delta accepted → ship the prompt change, run [`edd:run`](../run/SKILL.md) one more time to confirm no regression on `regressions.txt`.
- Delta rejected → roll back, return to [`edd:scope-evals`](../scope-evals/SKILL.md) (judge may be miscalibrated) or [`edd:scope-agent`](../scope-agent/SKILL.md) (promise may need rephrasing).
