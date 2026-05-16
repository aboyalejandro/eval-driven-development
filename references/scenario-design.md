# Designing scenarios from a branch diff

Scenarios test promises, not surfaces. Read `agent-analysis.md` and `evaluator-selection.md` first — the promise inventory is the input to this workflow, and you need the evaluator schema names before you can tag scenarios with the right judges. Don't design scenarios from a taxonomy; design them from what the agent claims to do.

## Workflow

1. Run `agent-analysis.md` extraction to get the promise inventory.
2. Run `git diff main...HEAD --stat` to list changed files.
3. Map changed files to affected promises (not to a surface category).
4. Generate scenario intents for each affected promise.
5. Expand intents to instances — multiple phrasings per intent.
6. Add regression scenarios from `regressions.txt` (baseline promises, always).
7. Keep total under 10 — fast feedback beats coverage.

## Intent vs instance

This distinction controls what you hardcode vs what Claude generates:

**Intent** — the promise being tested. Stable, comes from the promise inventory.
> "A user asks for article performance data — agent should fetch and cite real metrics."

**Instance** — a concrete message that exercises the intent. Generated, varied.
> "How are my latest articles performing?"
> "Which article got the most engagement last month?"
> "Tell me what's working in my recent posts."

Keep intents in `regressions.txt`. Generate instances on the fly from those intents. Running three instances of the same intent catches phrasing brittleness that a single scenario misses.

## From promise to scenario intent

For each affected promise, ask:

| Promise type | Scenario intent to derive |
|---|---|
| Structured output contract | A request that should produce the full prescribed shape |
| Tool-grounded response | A data question whose answer exists in the tool's output |
| Empty-result handling | A request where the tool will return nothing |
| Skill / routing | A message using the skill's trigger words verbatim |
| Skill / routing (negative) | An adjacent message that should *not* trigger the skill |
| Scope / refusal | An out-of-scope ask the agent should decline or redirect |
| Multi-turn memory | Two turns where turn 2 depends on context from turn 1 |

One intent per row. Don't add intents for promises the diff doesn't touch.

## Scenario shape

One intent per line in the file passed to `edd run`. Plain text or JSON.

```
# intent: article performance grounding
How are my latest articles performing?

# intent: empty result recovery
{"message": "Show me articles from 1995", "evaluators": ["your-recovery-evaluator"]}

# intent: skill routing (positive)
{"message": "What's my writing voice?", "evaluators": ["your-routing-evaluator"]}

# intent: skill routing (negative — should NOT trigger brand-voice)
{"message": "What should I write about next?", "evaluators": ["your-routing-evaluator"]}

# intent: multi-turn context retention
{"message": "Analyze my top notes", "followups": ["Now give me 3 ideas that build on those themes"], "evaluators": ["your-format-evaluator"]}
```

Evaluator names must match the schema names in your Opik project. Leave `evaluators` off to use the `--evaluators` flag from the CLI.

Write messages as a real user would type them, not as a test engineer would. Slightly malformed phrasing and incomplete sentences catch regressions that polished prompts miss.

## Regression set

`regressions.txt` holds baseline scenario intents — one concrete instance per intent, covering the 5–8 promises that define the agent's core identity (from `agent-analysis.md`). Run it alongside every diff. Don't add to it until an evaluator has survived 2+ calibrated runs.

## What not to put in the agenda

- Scenarios for promises the diff doesn't touch — neutral noise, wasted tokens.
- Multi-turn scenarios unless the diff touches session memory or follow-up routing.
- "All possible phrasings" — wording variants belong in the simulation dataset, not the setup loop.

## Aggression levels

The level determines how hard scenarios push the agent against its own harness, heuristics, and evaluators. Apply it when generating `scenarios.txt` from the promise inventory. Since the goal is to evaluate tool outputs (not just responses), higher levels should specifically stress the paths where tool calls might not fire, fire incompletely, or return unexpected shapes.

### Level 1 — Harness validation

Normal user flows. Exact trigger phrases from the skill definitions. Happy paths where data exists and the agent should succeed cleanly. Tests that the core harness works — right skill fires, tools are called, output structure is correct.

### Level 2 — Mixed

Level 1 scenarios plus: partial trigger phrases, adjacent intents that might activate the wrong skill, multi-turn sessions where context shifts mid-way, requests where a tool returns data but the agent might format it incompletely.

### Level 3 — Adversarial

Mostly edge cases designed to surface harness failures. Conflicting instructions, inputs near skill boundaries that might route incorrectly, scenarios where the agent might fabricate (empty result + specific-sounding ask), near-miss out-of-scope asks, requests that require multiple dependent tool calls where any one could be skipped. Focus: not "does the happy path work" but "where does the harness break."
