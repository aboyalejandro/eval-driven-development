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
| PATCH | `/traces/batch` | Body: `{ids, update: {tags_to_add: [...]}, merge_tags: true}` — bulk tag. Old POST shape returns 422. |
| GET | `/traces/{id}` | Returns trace incl. embedded `feedback_scores` array |
| PATCH | `/traces/{id}` | Update metadata — body must include `project_name` or returns 409 |
| GET | `/spans?project_name&trace_id` | Pull model id from first LLM span |

> Opik 1.x exposed `/traces/{id}/feedback-scores` separately; 2.x embeds scores
> on the trace itself. The legacy path now returns 405.

## Datasets

| Verb | Path | Notes |
|---|---|---|
| GET | `/datasets?name=<n>` | Resolve dataset id |
| POST | `/datasets` | Create. Body: `{id (uuid7!), name, description?, project_name?, tags?}`. `project_name` scopes dataset to project in UI; without it, dataset is workspace-level and invisible in the project Datasets tab. |
| DELETE | `/datasets/{id}` | Delete dataset |
| PUT | `/datasets/items` | Upsert items. Each item shape: `{id (uuid7), source: "manual", data: {...fields...}}`. Flat item dicts return 422. |
| GET | `/datasets/{id}/items` | Page raw items (no experiment join) |
| GET | `/datasets/{id}/items/experiments/items?experiment_ids=[…]` | Items joined with one experiment's outputs + scores |

> All entity IDs (dataset, item, experiment, optimization) must be **UUID v7**,
> not UUID v4. Python 3.14+ has `uuid.uuid7()`. UUID v4 returns 400 "id must be a version 7 UUID".

## Experiments

| Verb | Path | Notes |
|---|---|---|
| POST | `/experiments` | Pre-mint `id` (uuid7) so bulk items can target it. Body: `{id, dataset_name, name, project_id, optimization_id?, type, status, metadata, tags}` |
| PUT | `/experiments/items/bulk` | **PUT not POST** (POST returns 405). Body: `{experiment_id, dataset_name, experiment_name, items}`. Field names are snake_case — camelCase silently treated as blank. Items carry `dataset_item_id`, `trace_id`, `input`, `output`, `feedback_scores`. |
| GET | `/experiments/{id}` | Resolve dataset id, name, status |
| GET | `/experiments?name=<n>` | Find by name |

> Always pass `project_id` on experiment create. Without it, items land
> against the Opik default project and you lose the trace deep-links.
> Experiments cannot be deleted via the REST API (405) — delete from the UI.

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
to experiment items — `edd-run` polls them off the traces and
copies them onto the items so both the trace and experiment item carry the scores.

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
