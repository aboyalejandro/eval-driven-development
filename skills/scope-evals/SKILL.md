---
name: scope-evals
description: Configure manual-trigger judges in Opik — derive one evaluator dimension per promise, list what already exists, generate `_local/create_evaluators.py` for the gaps, run it. Output is `.edd/evaluator-plan.md` + judges live in Opik with `enabled=False, sampling_rate=0`. Invoke as `edd:scope-evals` or when the user says "set up judges", "create evaluators", "scope the evals". For *firing* judges and reading scores, see `edd:run`.
---

# edd:scope-evals — evaluator dimensions + Opik judges

Discovery step 2 of the eval pipeline. Reads the promise inventory, decides which judges are needed, reuses what exists, creates gaps.

## Preconditions

- `.edd/promises.md` exists (run [`edd:scope-agent`](../scope-agent/SKILL.md) first)
- Opik creds in `.env`: `OPIK_URL`, `OPIK_API_KEY`
- Opik project named in `.edd/session.json` (or ask the user — must be a dedicated **testing** project, not production)

## Steps

### 1. Derive dimensions from promises

For each line in `.edd/promises.md`, map to one evaluator dimension. Follow [references/evaluator-selection.md](../../references/evaluator-selection.md). Categories:

- **Trigger correctness** — did the agent fire the right skill/tool?
- **Output fidelity** — does the response match the promised shape?
- **Boundary respect** — does it refuse / escalate when the promise requires?
- **Tool usage** — were the right tools called in the right order?

Write derived dimensions to `.edd/evaluator-plan.md`:

```
- <Dimension Name> → covers promise: <surface>
  Variable paths: metadata.user_message, metadata.assistant_response, metadata.tools_called
  Scoring: 1 = explicitly verified, 0 = failed OR not applicable
```

### 2. List existing Opik evaluators

```python
import sys; sys.path.insert(0, 'scripts')
from shared.opik_client import OpikClient
c = OpikClient()
evs = c.get_evaluators().get('content', [])
for ev in evs:
    s = (ev.get('code', {}).get('schema') or [{}])[0]
    print(s.get('name', ev.get('name')))
```

Mark each dimension in `.edd/evaluator-plan.md` as **REUSE** (match exists) or **CREATE** (gap).

### 3. Generate `_local/create_evaluators.py`

One block per **CREATE** dimension. Template:

```python
from shared.opik_client import OpikClient
c = OpikClient()

c.create_evaluator(
    project_name="<opik-project>",
    name="<Dimension Name>",
    prompt="""You are scoring whether <promise>.

Score 1 if: <explicit success criteria, observable in the trace>
Score 0 if: <failure OR not applicable — anything we can't verify>

Trace input: {{metadata.user_message}}
Trace output: {{metadata.assistant_response}}
Tools called: {{metadata.tools_called}}

Return JSON: {"score": 0|1, "reason": "<one sentence>"}""",
    model="anthropic/claude-sonnet-4-6",
    enabled=False,        # manual-trigger only — judges run only when `edd score` triggers
    sampling_rate=0,      # do not auto-fire on production traces
)
```

Rules baked into the template:
- **Manual-trigger only.** `enabled=False, sampling_rate=0` — `edd score` fires the judge; nothing else does.
- **Read from `metadata.*`.** Enrichment populates these (see `_local/enrich_traces_<sdk>.py`); never wire the judge to native SDK trace paths.
- **Binary scoring.** 1 = explicitly verified correct, 0 = failed OR not applicable. No half-credit, no NA.

### 4. Run it

```bash
python _local/create_evaluators.py
```

Re-listing via `c.get_evaluators()` should now show every dimension from the plan.

### 5. Document variable paths

Append to `.edd/evaluator-plan.md` which trace paths each judge expects. This is what `_local/enrich_traces_<sdk>.py` must populate — `edd:run` reads this file to know whether enrichment is needed.

## Outputs

| File | Purpose |
|---|---|
| `.edd/evaluator-plan.md` | Dimension → promise mapping, REUSE/CREATE marks, variable paths |
| `_local/create_evaluators.py` | Idempotent script that creates missing judges in Opik |
| Opik project | Judges live here, manual-trigger mode |

## Anti-patterns

- Creating one mega-judge that scores "overall quality" — score per dimension or you lose signal.
- Leaving `enabled=True` or `sampling_rate>0` — judges will fire on every production trace and burn LLM spend.
- Re-creating judges that already exist — list first, diff, then create only gaps.
- Reading from native SDK trace paths in the judge prompt — write from `metadata.*` only.

See also: [pipeline anti-patterns](../CLAUDE.md#pipeline-anti-patterns) (global).

## Next

→ [`edd:run`](../run/SKILL.md) — fire scenarios, tag traces, score with these judges.
