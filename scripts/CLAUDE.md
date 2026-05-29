# scripts/ — framework engine

Python package that backs the `edd`, `edd-build`, `edd-run`, `edd-inspect` CLIs. Two phases (setup / simulation) over a shared Opik REST wrapper.

## Layout

| Path | CLAUDE | Role |
|---|---|---|
| [`setup/`](setup/CLAUDE.md) | yes | Inner loop — emit scenarios, tag traces, trigger judges, render score table |
| [`simulation/`](simulation/CLAUDE.md) | yes | Outer loop — build datasets, run experiments, inspect failures |
| [`shared/`](shared/CLAUDE.md) | yes | Opik REST client + settings singleton |
| [`metrics/`](metrics/CLAUDE.md) | yes | Deterministic code-based metrics — `BaseMetric` subclasses registered as `user_defined_metric_python` rules |
| `pyproject.toml` | — | Console scripts: `edd`, `edd-build`, `edd-run`, `edd-inspect`, `edd-metrics` |

## Install + activate

```bash
cd scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

All `edd*` commands assume the venv is active and run from **repo root**.

## Console scripts → modules

| CLI | Module |
|---|---|
| `edd` | [`setup/cli.py`](setup/CLAUDE.md) (Typer app with `run`, `score`, `check` subcommands) |
| `edd-build` | [`simulation/build_dataset.py`](simulation/CLAUDE.md) |
| `edd-run` | [`simulation/run_experiment.py`](simulation/CLAUDE.md) |
| `edd-inspect` | [`simulation/inspect_experiment.py`](simulation/CLAUDE.md) |
| `edd-metrics` | [`metrics/register.py`](metrics/CLAUDE.md) — register/update code metrics on an Opik project |

## Module boundaries

- `setup/` and `simulation/` both depend on `shared/`. They do **not** import from each other.
- `setup/agent.py` is the **only** runtime-specific file in the framework core, and even that loads a custom adapter from `_local/` via `AGENT_ADAPTER` env var. Do not hardcode runtime details in framework files.
- `shared/opik_client.py` is the single REST surface. If a script needs a new Opik endpoint, add the method here — don't sprinkle `httpx` calls across the codebase.

## Caveat — Opik REST coupling

The framework is tightly coupled to Opik's REST API. Endpoints are catalogued in [`../references/opik-endpoints.md`](../references/opik-endpoints.md). If a previously-working setup starts erroring after time has passed, suspect API drift first — check Opik release notes before debugging the framework.

## Up one level

- Root: [../CLAUDE.md](../CLAUDE.md) — repo overview
- Skills: [../skills/CLAUDE.md](../skills/CLAUDE.md) — workflow entry points
- References: [../references/CLAUDE.md](../references/CLAUDE.md) — decision guides
