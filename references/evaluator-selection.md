# Evaluator selection — decision tree

Pick the evaluator first. It drives scenario design, dataset shape, and what "passing" means. If you can't name the dimension the branch should move, the experiment isn't ready.

## Step 0 — derive dimensions from the agent

Before looking at what evaluators exist, derive what dimensions matter for *this* agent. Dimensions come from promises, not from a taxonomy.

Run the `agent-analysis.md` extraction. For each row in the promise inventory, draft a candidate dimension:

- Name it from the failure mode, not from a generic family: `article-grounding` not `Faithfulness`, `brand-voice-format` not `Format Compliance`.
- Write one sentence describing what a score of 1 looks like and one describing score 0.
- Note whether it's deterministic (code-based judge viable) or subjective (needs LLM-as-judge).

Only after this list is drafted should you check what exists in the project.

## Step 1 — list what's already there

Hit `/v1/private/automations/evaluators` (the CLI prints them via `opik_client.get_evaluators()`). Each rule's *schema name* — the `code.schema[0].name` field — is the canonical handle you'll pass as `--evaluator` everywhere downstream.

Map your derived dimensions to existing rules. Reuse where the rubric matches. Build new when it doesn't — don't stretch an existing judge to cover a dimension it wasn't calibrated for.

## Step 2 — check against generic families

Use this table as a completeness check, not a menu. If a dimension you derived maps to a family here, that's confirmation it's worth a stable evaluator. If nothing maps, the dimension is either agent-specific (fine) or not real (drop it).

| What the agent promises | Generic family to check against |
|---|---|
| Prescribed response shape / structured output | Format |
| Claims grounded in fetched data, not training | Grounding / Faithfulness |
| Correct tool called at the right time | Tool selection |
| Empty or error result handled without hallucination | Recovery |
| Off-topic asks declined or redirected | Scope / Safety |
| Correct skill or sub-agent triggered | Routing |
| Session context carried across turns | Memory / Persistence |

One dimension per row. If the diff touches more than one, pick the dominant one first and run the secondary as a follow-up experiment under the same optimization (see `experiment-grouping.md`).

## Step 3 — build if missing

If no existing evaluator fits, build one before continuing:

| Method | When |
|---|---|
| Calibrated judge (LLM-as-judge + human labels) | Subjective dimensions — need TPR/TNR alignment before trusting the score |
| Code-based judge | Deterministic checks: regex, JSON schema validation, presence of a tool call in the trace |

Don't run experiments against an uncalibrated LLM judge — you'll chase noise. Calibrate on 20–30 labeled trace pairs before treating the score as signal.

## Step 4 — staging readiness

Two modes for the same rule. Pick one per judge — don't mix.

**Manual-trigger mode (setup inner loop default):** `enabled=false`, `sampling_rate=0.0`. The framework's `trigger_evaluation` ignores both flags and fires the judge on exactly the traces you point at. Use this when sim traffic is the only thing you want scored — keeps the project clean of stray scores from concurrent dev sessions and avoids double-counting (auto-sample + manual trigger on the same trace).

**Auto-sample mode (production-parity):** `enabled=true`, `sampling_rate=1.0` (or fractional). Opik scores every matching trace as it lands, including production traffic. Use when you want sim and prod scored by the same rubric and the project receives both kinds of traffic.

Most teams start in manual-trigger mode for the inner loop, then enable auto-sampling per judge once the rubric is calibrated and they want it watching prod.

## Step 5 — naming hygiene

Give the schema name a stable, kebab-cased form derived from the agent's promise: `article-grounding`, `brand-voice-format`, `empty-result-recovery`. Every script in this repo treats that string as a primary key — renames cascade.

Avoid generic names (`compliance`, `quality`) — they describe nothing and make timelines unreadable.

## Anti-patterns

- **Starting from the taxonomy instead of the agent.** You end up evaluating dimensions the agent was never designed to satisfy.
- **Picking the evaluator after the experiment runs.** Scores become "what did this judge happen to fire on" instead of "did the branch move the needle on X".
- **Using an uncalibrated LLM judge as ground truth.** Two iterations in, you can't tell whether the prompt regressed or the judge drifted.
- **One mega-judge.** A judge that scores "everything" produces scores nobody trusts. Per-dimension judges are debuggable.
