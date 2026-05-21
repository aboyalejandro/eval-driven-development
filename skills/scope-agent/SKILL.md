---
name: scope-agent
description: Extract the agent's promise inventory and write baseline regression scenarios. Produces `.edd/promises.md` (one line per skill/tool/promise) and `regressions.txt` (5–8 baseline scenarios at aggression 1). Idempotent — skip if both exist and agent source is unchanged. Invoke as `edd:scope-agent` or when the user says "scope the agent", "extract promises", "build regressions".
---

# edd:scope-agent — promise inventory + regression baseline

Discovery step 1 of the eval pipeline. Reads the agent under test, lists what it promises, writes scenarios that cover each promise.

## Preconditions

- `AGENT_ENDPOINT` set in `.env` (HTTP URL of agent under test) — see [PREREQUISITES.md](../../PREREQUISITES.md)
- Agent source is readable (skill files, system prompt, tool definitions) — local path or repo clone

## When to invoke

- New agent, no `regressions.txt` yet
- Agent source changed (new skill added, system prompt rewrite, tool added/removed)
- User explicitly asks to refresh the promise inventory

**Skip** when `regressions.txt` and `.edd/promises.md` both exist and the agent source's last-modified time is older than `.edd/promises.md`. Re-deriving wastes tokens and drifts the baseline.

## Step 1 — Locate agent source

Ask the user for the path if not in current repo. Common shapes:
- Single system prompt file
- Multi-skill agent (Agno/OpenAI Agents/Anthropic SDK) — skills + tool list + router
- HTTP service — read the route handler + downstream skill loader

## Step 2 — Extract promises

Follow [references/agent-analysis.md](../../references/agent-analysis.md). For each skill / tool / prompt section, write one line in `.edd/promises.md`:

```
- <surface>: <what it promises to do> → <observable signal>
```

Example:
```
- summarize_thread: condenses Slack thread to <=3 bullets preserving named entities → output has <=3 bullets, mentions every @user from input
- escalate_to_human: hands off when confidence <0.7 OR user requests human → response includes handoff phrase, no further tool calls
```

Each promise becomes one evaluator dimension downstream (`edd:scope-evals` consumes this file).

## Step 3 — Write `regressions.txt`

One baseline scenario per core promise, 5–8 lines total. Follow [references/scenario-design.md](../../references/scenario-design.md) — use aggression level 1 (harness validation, happy path). Format: plain string per line, or JSON for scenarios that need `context` / `followups` / `evaluators`.

```
What did the team ship last sprint?
{"scenario": "Escalate this to a human", "evaluators": ["Escalation Trigger"]}
```

`regressions.txt` is gitignored at the framework level — **commit it in your fork or working branch**. It persists across sessions and protects against regressions.

## Step 4 — Lint the scenarios before writing

Two checks every scenario (regressions + any `scenarios.txt` you'll author later) must pass. Both run before the file is final.

### Check A — every scenario hits a named promise

Walk each scenario message and identify the surface it exercises. Cross-reference against `.edd/promises.md`. If a scenario doesn't map to any line in that file, the scenario is testing capability the agent doesn't have — every judge will score 0, the experiment will look catastrophic, and the diagnosis will mislead. Drop it or open a tooling task; do not promote it to a regression.

### Check B — flag unbounded plurals

Read [references/scenario-design.md § Blast-radius hygiene](../../references/scenario-design.md#blast-radius-hygiene--cap-result-sets). Reject any scenario whose phrasing reads as unbounded:

- contains `all`, `every`, `across the board`, or an unqualified plural noun (`articles`, `customers`, `tickets`)
- asks to `rank`, `compare`, or `list` without a `top N` / `last N` / `last N days` anchor
- searches without a result-count cap

When you catch one, rewrite it with an explicit cap before saving. The agent will obediently fan out to 50+ tool calls otherwise, blowing trace span counts and judge context windows.

## Step 5 — Update `.edd/session.json`

If the router hasn't populated it yet, write minimal state:
```json
{ "topic": "<slug-from-hypothesis>", "branch_tag": "<git-branch>" }
```

## Outputs

| File | Purpose |
|---|---|
| `.edd/promises.md` | One-line per surface — fed to `edd:scope-evals` |
| `regressions.txt` | 5–8 baseline scenarios at aggression 1 — fed to `edd:run` |

## Anti-patterns

- Writing 20+ regression scenarios — keep it ≤8. Coverage, not volume.
- Including diff-specific scenarios — those live in `scenarios.txt`, not `regressions.txt`.
- Skipping the inventory and jumping to scenarios — the inventory is what evaluator selection consumes.
- Scenarios that don't map to any promise. Skipping Step 4 Check A produces 0.00 scorecards that look like prompt failures but are capability gaps.
- Unbounded plurals ("show me all", "rank my X") — see Step 4 Check B and the blast-radius hygiene section in scenario-design.md.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global).

## Next

→ [`edd:scope-evals`](../scope-evals/SKILL.md) — turn promises into Opik judges.
