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
| PUT | `/datasets/{id}` | Update dataset metadata. Body `DatasetUpdate`: `name` **required** on every call (pass the current name even when only description/tags change), `description?` (max 255 chars), `visibility?` (`private`/`public`), `tags?`. Returns 204. |
| DELETE | `/datasets/{id}` | Delete dataset |
| PUT | `/datasets/items` | Upsert items. Each item shape: `{id (uuid7), source: "manual", data: {...fields...}}`. Flat item dicts return 422. |
| GET | `/datasets/{id}/items` | Page raw items (no experiment join) |
| GET | `/datasets/{id}/items/experiments/items?experiment_ids=[…]` | Items joined with one experiment's outputs + scores |
| POST | `/datasets/{id}/expansions` | AI-driven synthetic expansion. Dataset id is a **path param** (plural `expansions`). Body: `{model, sample_count?, preserve_fields?, variation_instructions?, custom_prompt?, max_completion_tokens?}`. Returns `{generated_samples: [...], model, total_generated, generation_time}` where each generated sample is a full `DatasetItem` (`{id, source, data, ...}`) — caller **must unwrap `data` before re-inserting** via `PUT /datasets/items` or items end up double-wrapped at `data.data.<field>`. Same primitive as the UI's "Expand with AI" button. |

> All entity IDs (dataset, item, experiment) must be **UUID v7**,
> not UUID v4. Python 3.14+ has `uuid.uuid7()`. UUID v4 returns 400 "id must be a version 7 UUID".

## Experiments

| Verb | Path | Notes |
|---|---|---|
| POST | `/experiments` | Pre-mint `id` (uuid7) so bulk items can target it. Body: `{id, dataset_name, name, project_id, type, status, metadata, tags}` |
| PUT | `/experiments/items/bulk` | **PUT not POST** (POST returns 405). Body: `{experiment_id, dataset_name, experiment_name, items}`. Field names are snake_case — camelCase silently treated as blank. Items carry `dataset_item_id`, `trace_id`, `input`, `output`, `feedback_scores`. |
| GET | `/experiments/{id}` | Resolve dataset id, name, status |
| GET | `/experiments?name=<n>` | Find by name |

> Always pass `project_id` on experiment create. Without it, items land
> against the Opik default project and you lose the trace deep-links.
> Experiments cannot be deleted via the REST API (405) — delete from the UI.

## Manual evaluation (automation rules)

| Verb | Path | Notes |
|---|---|---|
| GET | `/automations/evaluators?size=500` | List rules; `code.schema[0].name` is the canonical schema name |
| POST | `/automations/evaluators` | Create rule; type `llm_as_judge` or `user_defined_metric_python` |
| PATCH | `/automations/evaluators/{id}` | Update rule metadata. **Does NOT replace `code` field** — Opik ignores it on PATCH. To swap metric source: `delete_evaluators_by_name` + re-POST. |
| DELETE | `/automations/evaluator-rules` (batch) | Delete by ids list |
| GET | `/automations/evaluators/{id}/logs` | Per-rule execution logs — **first place to look when scores never land** |
| POST | `/manual-evaluation/traces` | Body: `{project_id, entity_ids, rule_ids, entity_type: "trace"}` — async writeback |

> Opik 1.x triggered evaluation via `POST /automations/evaluators/run` with
> `trace_ids`; 2.x uses `POST /manual-evaluation/traces` with `entity_ids`
> + `entity_type`. The old path returns 405.

If scores never appear, fetch `/automations/evaluators/{id}/logs` — the
most common cause is "API key not configured for LLM" when the judge
model's provider isn't credentialed in the workspace.

## Score storage — two planes, no auto-sync

Opik stores feedback scores in two unsynced places:

| Plane | Where it lives | Visible in | Written by |
|---|---|---|---|
| **Trace plane** | `trace.feedback_scores[]` (embedded on the trace) | Traces table, trace detail view | `POST /manual-evaluation/traces`; online_scoring rules |
| **Experiment plane** | `experiment_item.feedback_scores[]` | Experiment Compare UI, scorecard | `PUT /experiments/items/bulk` body |

Writing one **never** updates the other. `edd-run` works around this by
polling scores off the trace (`get_trace_scores`) and copying them into
the bulk items payload — without that copy, the Compare UI is empty
even though the trace is scored.

**Consequences:**

- `edd-inspect` reads experiment-plane scores only. Judges firing on a
  trace *after* `edd-run` completes never reach the experiment item —
  re-run `edd-run` (or extend the client with a reconcile pass) to re-sync.
- Annotations don't propagate. A reviewer's note in the Compare UI is
  invisible from the trace, and vice versa.
- For variant comparisons across experiments, trust experiment-plane
  only. Trace-plane scores can include stale runs from before the
  experiment was frozen.

## Reference URL patterns

| What | URL |
|---|---|
| Experiment | `<OPIK_URL>/experiments/<id>` |
| Trace | `<OPIK_URL>/traces/<id>` |
| Dataset | `<OPIK_URL>/datasets/<id>` |

`OPIK_URL` is the deployment root (`https://opik.example.com`), not the
`/v1/private` API base.

## See also

- [`../scripts/shared/CLAUDE.md`](../scripts/shared/CLAUDE.md) — `OpikClient` wraps these endpoints; add methods here if a new one is needed
