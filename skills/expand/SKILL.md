---
name: expand
description: AI-driven expansion of an existing Opik dataset — Claude reads the seed items, the agent's promise inventory, the evaluator plan, and the session aggression, then derives `variation_instructions` and `preserve_fields` that target the dataset's actual coverage gaps (not generic LLM filler). Wraps `edd-expand` against Opik's `/datasets/expand` endpoint. Invoke as `edd:expand` or when the user says "grow the dataset", "expand with AI", "add synthetic scenarios", "more coverage". For *building the seed dataset from sim traces*, see `edd:experiment`.
---

# edd:expand — AI-driven dataset growth

Opik's `/datasets/expand` endpoint is the AI-side primitive. This skill is the agent-side intelligence that picks the right params for *your* dataset.

The point: generic synthetic data is noise. The skill exists because the params that make expansion useful (`variation_instructions`, `preserve_fields`, `custom_prompt`) need agent-specific signal — the promises being tested, the evaluator dimensions in play, the coverage gap the seed dataset has *right now*.

## Preconditions

- A seed dataset exists in Opik (created by [`edd:experiment`](../experiment/SKILL.md) **Phase D**)
- **No experiment has run on this dataset version yet** ([`edd:experiment`](../experiment/SKILL.md) Phase E has not been called). Expansion is a hard gate before judging — never after. Mid-experiment growth destroys apples-to-apples comparison; if you already judged, bump the dataset version and rebuild before expanding.
- `.edd/promises.md` exists ([`edd:scope-agent`](../scope-agent/SKILL.md))
- `.edd/evaluator-plan.md` exists ([`edd:scope-evals`](../scope-evals/SKILL.md))
- `.edd/session.json` has `topic` + `aggression`
- venv active

## Step 1 — Inspect the seed dataset

Stream up to 30 items via `OpikClient.stream_dataset_items`. For each item record:

- Which fields appear in 100% vs <100% of items (shape contract)
- A frequency map of user-message intents (clustering by keyword / promise hit)
- Whether `source_trace_id` is present and pointing at real sim traces

Compare the distribution to the target mix from [references/dataset-design.md](../../references/dataset-design.md):

| Bucket | Target % | What "underrepresented" looks like |
|---|---|---|
| Happy path | 30 | Almost all items use exact trigger phrases |
| Wording variants | 20 | Every user_message follows the same template |
| Edge cases | 15 | No items with empty/missing data references |
| Adversarial | 15 | No ambiguity, no conflicting intents |
| Multi-turn | 10 | All items are single-turn |
| Negatives | 10 | No out-of-scope refusals tested |

Write the gap analysis to `.edd/expansion-plan.md`. Identify the **one** bucket that's farthest below target and target *that* with the expansion.

## Step 2 — Derive params from the gap

For each `--<flag>`, derive from what Step 1 found.

**`--preserve-field`** — every field that appeared in 100% of seed items, EXCLUDING `source_trace_id` (synthetic items won't have a real trace). Typical: `user_message assistant_response`. If the seed items carry a structured `trace_metadata` blob the judges read, preserve that too.

**`--variation-instructions`** — agent-specific, gap-targeted, and grounded in the promise inventory. Bad: "make some edge cases." Good: "user_message asks the agent to summarize an article that doesn't exist in the user's content library — the agent should refuse without inventing content (recovery promise from `.edd/promises.md`). Use real-sounding article titles. assistant_response should be empty or a placeholder; the experiment scoring will fill it from the real agent."

Aggression-level defaults if no gap dominates:

| Session aggression | Default variation_instructions starter |
|---|---|
| 1 | "Rephrase the user_message with minor wording changes — same intent, different phrasing. Keep the item shape identical." |
| 2 | "Generate edge cases: empty results, adjacent intents that look similar to the target promises, partial trigger phrases. Keep the same fields, only vary user_message." |
| 3 | "Adversarial wordings: ambiguous scope, conflicting instructions in the same message, multi-turn context that shifts mid-conversation. Preserve item shape." |

Always rewrite the starter with the agent's actual vocabulary (skill names, tool names, domain terms) — pull from `.edd/promises.md`. Generic instructions produce generic items.

**`--model`** — pick from what your workspace has API keys for. Default `anthropic/claude-sonnet-4-6` for variation work; `openai/gpt-4o` is a fine alternative. Smaller models (haiku/mini) accelerate dry-runs.

**`--count`** — scale to the gap, not arbitrary. If happy-path is 80% of 50 items and target is 30%, you need ~67 non-happy items. Add in batches (10–20 at a time) and re-inspect coverage between rounds.

## Step 3 — Dry-run

```bash
edd-expand \
  --dataset-name <project>-<topic>-v<N> \
  --model "anthropic/claude-sonnet-4-6" \
  --count 5 \
  --preserve-field user_message --preserve-field assistant_response \
  --variation-instructions "<derived in Step 2>" \
  --dry-run
```

Reads the first 3 generated samples to stdout. Confirm:

- **Shape** — every preserved field appears with the same type
- **Vocabulary** — uses the agent's domain terms, not generic LLM filler
- **Targeting** — actually exercises the gap you identified, not the bucket that was already saturated

If any of the three fails, refine the variation_instructions or switch model. Re-run dry. Cheap.

## Step 4 — Persist

Same command without `--dry-run`. The CLI:

1. Calls Opik `/datasets/expand` → receives generated samples
2. Inserts them via `OpikClient.insert_dataset_items` (same write path as `edd-build`)
3. Prints dataset URL

Update `.edd/session.json.dataset_name` only if you bumped the version (Step 5).

## Step 5 — Version decision

Whether to bump `v<N>` depends on what the expansion added:

| Expansion added | Bump `v<N>`? |
|---|---|
| More items of an existing shape | No — additive growth is fine |
| A new field the judges should read | Yes — item shape changed |
| Items the judges *can't* score (missing required field) | No — fix the variation_instructions and re-expand instead |

If you bump, build a new dataset (`edd-build` against the same trace set with a new `--dataset-name`) and expand from there. Cross-version comparisons are noise.

## Anti-patterns

- **Expanding after judges already ran on the dataset.** The whole point of expand-before-judge is one paid scoring pass on the final shape. Adding items post-judge means re-judging from scratch — bump the dataset version and rebuild instead. See the [hard ordering rule](../CLAUDE.md#pipeline-dag).
- **Skipping inspection — calling `/datasets/expand` without reading seed items first.** The result is generic LLM filler with no relationship to the agent's promises. Always Step 1 first.
- **Generic variation_instructions ("make some edge cases").** The endpoint optimises for the prompt it receives; vague prompts produce vague items. Use the agent's actual skill names + tool names + domain terms.
- **Preserving `source_trace_id`** — synthetic items don't have a real trace; preserving the field tells the LLM to invent trace IDs that won't deep-link.
- **Skipping `--dry-run`** — every expansion costs LLM tokens and pollutes the dataset if it goes wrong.
- **Large `--count` on first run** — start at 5–10, scale only after dry-run confirms targeting. Polluted datasets are hard to clean.
- **Re-expanding without re-inspecting coverage.** Two rounds of expansion targeting the same gap can overshoot — the bucket flips from underrepresented to dominant.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global).

## Next

→ Return to [`edd:experiment`](../experiment/SKILL.md) **Phase E** to judge the expanded dataset. The expansion was the gate; judging is the next paid step, run only on the final shape.
