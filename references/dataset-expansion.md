# Dataset expansion — AI-driven growth on an existing dataset

Opik 2.x ships an `/datasets/expand` endpoint that generates synthetic items by sending the seed dataset's shape + content to an LLM. This is the same primitive the Opik UI's "Expand with AI" button hits. EDD wraps it as `edd-expand`; the [`edd:expand`](../skills/expand/SKILL.md) skill drives the params.

## When to expand

| Situation | Expand? |
|---|---|
| Sim batch is small (<20 items) and the judge thinks everything is happy-path | **Yes** — boost coverage before running an experiment |
| Dataset is large but skewed toward one bucket | **Yes** — target the underrepresented bucket |
| You need adversarial wording variants on existing intents | **Yes** — that's exactly what `variation_instructions` is for |
| You haven't run any real sim traces yet | **No** — expansion needs a seed shape; build a small real-trace dataset first |
| The judges aren't calibrated yet | **No** — uncalibrated judges + synthetic items compounds noise |
| You're mid-experiment comparing variants | **No** — changing the dataset under an in-flight comparison destroys the apples-to-apples |

## Two-step flow — generate → review → persist

The endpoint returns generated samples but does **not** auto-insert. Mirrors the UI's "draft before saving."

1. **Dry-run** — `edd-expand --dry-run` prints the first 3 samples to stdout. Read them. Decide.
2. **Persist** — same command without `--dry-run`. The CLI writes via `OpikClient.insert_dataset_items` (the same path `edd-build` uses).

If samples look generic or off-target, refine `--variation-instructions` and dry-run again. Cheap.

## Params — what each lever does

| Param | Purpose |
|---|---|
| `--dataset-name` | Seed dataset to expand from. Items must already exist. |
| `--model` | LLM doing the generation (`anthropic/claude-sonnet-4-6`, `openai/gpt-4o`, etc.). Workspace must have the corresponding API key. |
| `--count` | How many synthetic items to ask for. Server caps may apply. |
| `--preserve-field` | Field name(s) whose pattern the LLM must keep. Repeatable. Pass every field your judges read. |
| `--variation-instructions` | Free-form steering — agent-specific, gap-targeted. |
| `--custom-prompt` | Full prompt override. Use when `--variation-instructions` isn't enough (e.g. multi-turn templates that need a worked example). |
| `--max-tokens` | Required for Anthropic models — defaults to 4000 server-side. |

## Aggression → variation_instructions defaults

Use as a starting point; rewrite with the agent's actual vocabulary.

| Aggression | Default starter |
|---|---|
| 1 | Rephrase user_message with minor wording changes; same intent. |
| 2 | Edge cases — empty results, partial trigger phrases, adjacent intents. |
| 3 | Adversarial — ambiguous scope, conflicting instructions, multi-turn context shifts. |

The defaults aren't enough on their own. Generic instructions produce generic items. The skill rewrites them with skill names, tool names, and domain terms from the promise inventory.

## preserve_fields gotchas

- **Always preserve the fields the judges read.** If `metadata.user_message` is the judge input, `user_message` should be in `preserve_fields`. Otherwise the LLM might rename or restructure it.
- **Never preserve `source_trace_id`.** Synthetic items don't have a real sim trace; preserving forces the LLM to invent IDs that won't deep-link in the Opik UI. Leave it absent.
- **`trace_metadata` is preserve-worthy if your judges read enrichment keys** (tool counts, span shapes). Otherwise omit.

## Anti-patterns

- **Calling `/datasets/expand` without inspecting seed items first.** Generic LLM filler. The whole point of the skill is to derive agent-specific steering.
- **Generic variation_instructions** ("make some edge cases"). The LLM optimises for what it's told; vague prompts → vague items.
- **Large `--count` on the first run.** Start at 5–10; scale only after dry-run confirms targeting. Polluted datasets are hard to clean — Opik's delete endpoint is unreliable on items, UI sweep is manual.
- **Expanding a dataset mid-experiment comparison.** Pin the dataset version per experiment; if you need more coverage, build a new version (`<topic>-v2`) and start a fresh comparison.
- **Re-running expansion targeting the same gap.** Two rounds can overshoot — the underrepresented bucket flips to dominant. Re-inspect coverage between rounds.

## See also

- [`dataset-design.md`](dataset-design.md) — target coverage mix (the table the skill compares actual vs target against)
- [`evaluator-selection.md`](evaluator-selection.md) — preserve_fields must match what your judges read
- [`opik-endpoints.md`](opik-endpoints.md) — `/datasets/expand` endpoint shape
- [`../skills/expand/SKILL.md`](../skills/expand/SKILL.md) — skill that drives `edd-expand` with derived params
- [`../skills/experiment/SKILL.md`](../skills/experiment/SKILL.md) — builds the seed dataset; runs the experiment that scores the expanded one
