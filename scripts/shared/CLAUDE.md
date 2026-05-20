# scripts/shared/ — Opik REST client + settings

Single source of truth for Opik API access and environment-variable reads. Both `setup/` and `simulation/` import from here.

## Files

| File | Role |
|---|---|
| `opik_client.py` | `OpikClient` — narrow REST wrapper (traces, datasets, experiments, evaluators) |
| `settings.py` | `Settings` dataclass — read-only snapshot of env vars taken at import time |
| `session.py` | `.edd/session.json` reader + branch guard. `assert_active_branch()` refuses main/master; `session_tags()` returns empty — branch name is the single identity tag |
| `__init__.py` | Re-exports `OpikClient` and `settings` singleton |

## `OpikClient` surface

Methods exist for **every** endpoint the framework needs and nothing else. Categories:

- **Traces** — `search_traces`, `batch_tag`, `get_feedback_scores`, `get_spans` (for run-time model lookup)
- **Evaluators** — `get_evaluators` (list automation rules), `trigger_evaluator` (manual run)
- **Datasets** — `get_dataset_by_name`, `upsert_dataset_items`, `get_dataset_items_with_experiment_outputs`, `expand_dataset` (AI synthetic generation)
- **Experiments** — `create_experiment` (pre-minted id), `add_experiment_items`

If you need an endpoint that isn't here, **add the method to this class**. Do not sprinkle `httpx` calls across other modules.

## `Settings`

All env-var reads in the framework go through this module. Import the `settings` singleton — never call `os.getenv` or `os.environ` directly in library code.

Required env vars:
- `OPIK_URL` — Opik base URL
- `OPIK_API_KEY` — auth header value
- `OPIK_OTLP_ENDPOINT` — used by the agent (not this client) to ship traces
- `AGENT_ENDPOINT` — HTTP URL of agent under test
- `OPIK_WORKSPACE` — required by Comet-hosted Opik; ignored by self-hosted
- `AGENT_ADAPTER` — optional; `module:function` to override default HTTP adapter

## Caveat

The framework is **tightly coupled** to Opik's REST API. See [`../../references/opik-endpoints.md`](../../references/opik-endpoints.md) for the catalogue of endpoints used. If Opik bumps a version and shapes change, this is the file that needs patching.

## Up one level

- Engine: [../CLAUDE.md](../CLAUDE.md)
