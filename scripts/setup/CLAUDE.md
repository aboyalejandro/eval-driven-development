# scripts/setup/ — inner loop

Backs the `edd` CLI. Emits scenarios at the agent, tags traces with `sim-<branch>`, triggers manual judges, polls scores, renders the table.

## Files

| File | Role | Edit? |
|---|---|---|
| `cli.py` | Typer app — `edd run`, `edd score`, `edd check` | rarely |
| `agent.py` | **Framework core** — generic HTTP adapter; loads `AGENT_ADAPTER` env var to override | **do not edit**; put custom adapters in `_local/my_adapter.py` |
| `results.py` | Polls Opik for feedback scores, dedupes to latest-per-judge, renders the score table | rarely |
| `__init__.py` | Re-exports `create_agent`, `run_scenario` | — |

## Subcommands

### `edd check`
Verifies Opik connectivity (`OPIK_URL` + `OPIK_API_KEY`) and that `AGENT_ENDPOINT` resolves.

### `edd run <scenarios>`
- Single string: emit one scenario.
- File path: one scenario per line; plain string or JSON with `context`, `followups`, `evaluators`.
- `--wait` + `--evaluators "<names>"`: emit, trigger judges immediately, poll, print table. **Only safe when judges can read raw trace shape — no enrichment step.**
- Without `--wait`: emit + tag, return immediately. Caller is expected to run enrichment then `edd score`.

**Branch guard.** `edd run` refuses to emit traces when the current git branch is `main` / `master` / detached — prevents accidental `sim-main` tagging. Override with `--allow-main` if legitimately needed.

**Tags applied to every emitted trace** (via `batch_update_traces`):
- `run-<8-char run id>` — uniquely identifies one `edd run` invocation
- `sim-<branch>` — join key for `edd-build`
- `topic-<topic>`, `mode-<n>`, `aggression-<n>` — propagated from `.edd/session.json` when present (see [`shared/session.py`](../shared/CLAUDE.md))

### `edd score --since <minutes>`
Triggers `--evaluators` on every trace tagged `sim-<branch>` within the time window, polls until scores land or timeout, prints the per-dimension table via `results.py`.

## Trace tagging convention

`sim-<branch>` is **always** the join key between setup and simulation. If you fork the CLI, preserve this — `simulation/build_dataset.py` filters traces by this tag.

## Custom HTTP adapter (`_local/my_adapter.py`)

Set `AGENT_ADAPTER=_local.my_adapter:create_agent` in `.env`. The adapter must expose:

```python
def create_agent(session_id: str, run_id: str, context: dict | None):
    ...
    return Agent()   # must have .arun(message) -> SimpleNamespace(content=<str>)
```

See [`../../PREREQUISITES.md`](../../PREREQUISITES.md) for the full contract.

## Up one level

- Engine: [../CLAUDE.md](../CLAUDE.md)
- Skill that uses this: [`edd:run`](../../skills/run/SKILL.md)
