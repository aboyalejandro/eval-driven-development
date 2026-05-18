---
description: Extract a promise inventory from agent source (skills, system prompt, tools) and write baseline regression scenarios. Output is `regressions.txt` at repo root + `.edd/promises.md` (inventory cache). Idempotent — skip if `regressions.txt` exists and agent source hasn't changed. Invoke as `edd:scope-agent` or when the user says "scope the agent", "extract promises", "build regressions".
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

## Steps

### 1. Locate agent source

Ask the user for the path if not in current repo. Common shapes:
- Single system prompt file
- Multi-skill agent (Agno/OpenAI Agents/Anthropic SDK) — skills + tool list + router
- HTTP service — read the route handler + downstream skill loader

### 2. Extract promises

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

### 3. Write `regressions.txt`

One baseline scenario per core promise, 5–8 lines total. Follow [references/scenario-design.md](../../references/scenario-design.md) — use aggression level 1 (harness validation, happy path). Format: plain string per line, or JSON for scenarios that need `context` / `followups` / `evaluators`.

```
What did the team ship last sprint?
{"scenario": "Escalate this to a human", "evaluators": ["Escalation Trigger"]}
```

`regressions.txt` is gitignored at the framework level — **commit it in your fork or working branch**. It persists across sessions and protects against regressions.

### 4. Update `.edd/session.json`

If the router hasn't populated it yet, write minimal state:
```json
{ "topic": "<slug-from-hypothesis>", "branch_tag": "sim-<git-branch>" }
```

## Outputs

| File | Purpose |
|---|---|
| `.edd/promises.md` | One-line per surface — fed to `edd:scope-evals` |
| `regressions.txt` | 5–8 baseline scenarios at aggression 1 — fed to `edd:run` |

## Anti-patterns

- Writing 20+ regression scenarios — keep it ≤8. Coverage, not volume.
- Including diff-specific scenarios — those live in `scenarios.txt`, not `regressions.txt`.
- Re-running scope-agent every session — check timestamps first.
- Skipping the inventory and jumping to scenarios — the inventory is what evaluator selection consumes.

## Next

→ [`edd:scope-evals`](../scope-evals/SKILL.md) — turn promises into Opik judges.
