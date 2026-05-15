# Opik REST cheatsheet — endpoints these scripts use

Base path is always `/v1/private/...`. Auth is the Bearer/raw token in the
`Authorization` header (see `opik_client.OpikClient`).

## Projects

| Verb | Path | Notes |
|---|---|---|
| GET | `/projects?name=<n>` | Resolve `project_id` for `manual-evaluation` |

## Traces

| Verb | Path | Notes |
|---|---|---|
| GET | `/traces?project_name&filters&size` | Time-window + tag filter |
| POST | `/traces/batch` | Body: `{trace_ids, tags_to_add}` — bulk tag |
| GET | `/traces/{id}` | Returns trace incl. embedded `feedback_scores` array |
| GET | `/spans?project_name&trace_id` | Pull model id from first LLM span |

> Opik 1.x exposed `/traces/{id}/feedback-scores` separately; 2.x embeds scores
> on the trace itself. The legacy path now returns 405.

## Datasets

| Verb | Path | Notes |
|---|---|---|
| GET | `/datasets?name=<n>` | Resolve dataset id |
| POST | `/datasets` | Create (caller mints `id`) |
| PUT | `/datasets/items` | Upsert items by their `id` |
| GET | `/datasets/{id}/items` | Page raw items (no experiment join) |
| GET | `/datasets/{id}/items/experiments/items?experiment_ids=[…]` | Items joined with one experiment's outputs + scores |

## Experiments

| Verb | Path | Notes |
|---|---|---|
| POST | `/experiments` | Pre-mint `id` (UUID) so bulk items can target it. Body: `{id, dataset_name, name, project_id, optimization_id?, type, status, metadata, tags}` |
| POST | `/experiments/items/bulk` | Body: `{experiment_id, items}`. Items carry `dataset_item_id`, `trace_id`, `input`, `output`, `feedback_scores` |
| GET | `/experiments/{id}` | Resolve dataset id, name, status |
| GET | `/experiments?name=<n>` | Find by name |

> Always pass `project_id` on experiment create. Without it, items land
> against the Opik default project and you lose the trace deep-links.

## Optimizations

| Verb | Path | Notes |
|---|---|---|
| GET | `/optimizations?name&dataset_id` | Find existing (idempotent grouping) |
| PUT | `/optimizations` | Upsert (caller mints `id` for reuse) |
| GET | `/optimizations/{id}` | Status + linked experiments |

`optimization_id` on `create_experiment` is the only field linking a run
to the timeline view. Setting it after the fact requires a manual update.

## Manual evaluation (automation rules)

| Verb | Path | Notes |
|---|---|---|
| GET | `/automations/evaluators?size=500` | List rules; `code.schema[0].name` is the canonical schema name |
| POST | `/automations/evaluators` | Create rule; type `llm_as_judge` or `user_defined_metric_python` |
| DELETE | `/automations/evaluator-rules` (batch) | Delete by ids list |
| GET | `/automations/evaluators/{id}/logs` | Per-rule execution logs — **first place to look when scores never land** |
| POST | `/manual-evaluation/traces` | Body: `{project_id, entity_ids, rule_ids, entity_type: "trace"}` — async writeback |

> Opik 1.x triggered evaluation via `POST /automations/evaluators/run` with
> `trace_ids`; 2.x uses `POST /manual-evaluation/traces` with `entity_ids`
> + `entity_type`. The old path returns 405.

Triggered scores write to **trace-level** `feedback_scores` (embedded on
the trace, not a separate endpoint in 2.x). They do *not* auto-propagate
to experiment items — `run_experiment.py` polls them off the traces and
copies them onto the items so both layers carry the data.

If scores never appear, fetch `/automations/evaluators/{id}/logs` — the
most common cause is "API key not configured for LLM" when the judge
model's provider isn't credentialed in the workspace.

## Reference URL patterns

| What | URL |
|---|---|
| Experiment | `<OPIK_URL>/experiments/<id>` |
| Optimization | `<OPIK_URL>/optimizations/<id>` |
| Trace | `<OPIK_URL>/traces/<id>` |
| Dataset | `<OPIK_URL>/datasets/<id>` |

`OPIK_URL` is the deployment root (`https://opik.example.com`), not the
`/v1/private` API base.
