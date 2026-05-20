"""Opik REST wrapper — narrow surface, endpoints documented in scripts/shared/CLAUDE.md."""

import logging

import httpx
from fastuuid import uuid7

from shared.settings import settings

log = logging.getLogger(__name__)


class OpikClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base = (base_url or settings.opik_url).rstrip("/")
        self.headers = {"Authorization": api_key or settings.opik_api_key}
        # Comet-hosted Opik requires workspace scoping for REST calls; self-hosted ignores it.
        if settings.opik_workspace:
            self.headers["Comet-Workspace"] = settings.opik_workspace

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Execute an HTTP request and return the parsed JSON body."""
        kwargs.setdefault("timeout", 30.0)
        log.debug("%s %s", method, path)
        r = httpx.request(method, f"{self.base}{path}", headers=self.headers, **kwargs)
        if r.status_code >= 400:
            # Surface response body — Opik returns useful validation details here.
            raise httpx.HTTPStatusError(
                f"{r.status_code} {r.reason_phrase} on {method} {path}: {r.text[:400]}",
                request=r.request,
                response=r,
            )
        return r.json() if r.content else {}

    # --- projects ---

    def get_project_id(self, name: str) -> str:
        """Return the UUID of a project by name, raising ValueError if not found."""
        data = self._request("GET", "/v1/private/projects", params={"name": name})
        for p in data.get("content", []):
            if p["name"] == name:
                return p["id"]
        raise ValueError(f"project not found: {name}")

    # --- traces ---

    def search_traces(
        self,
        project: str,
        from_time: str,
        extra_filters: list[dict] | None = None,
    ) -> list[dict]:
        """Time-window trace search. extra_filters appends to the start_time filter."""
        import json as _json

        filters = [
            {"field": "start_time", "operator": ">=", "value": from_time},
            *(extra_filters or []),
        ]
        data = self._request(
            "GET",
            "/v1/private/traces",
            params={
                "project_name": project,
                "filters": _json.dumps(filters),
                "size": 500,
            },
        )
        return data.get("content", [])

    def batch_update_traces(
        self, trace_ids: list[str], project: str, tags_to_add: list[str]
    ) -> None:
        """Append tags to a batch of traces without overwriting existing ones."""
        # Opik 2.x: PATCH with `{ids, update, merge_tags}` shape. `tags_to_add`
        # lives inside the `update` body. Old POST {trace_ids, tags_to_add}
        # returns 422 "traces must not be null".
        self._request(
            "PATCH",
            "/v1/private/traces/batch",
            json={
                "ids": trace_ids,
                "update": {"tags_to_add": tags_to_add},
                "merge_tags": True,
            },
        )

    def get_trace_scores(self, trace_id: str) -> list[dict]:
        """Return feedback scores embedded on a trace (Opik 2.x stores them on the trace object)."""
        # `/traces/{id}/feedback-scores` was removed in Opik 2.x — scores are now
        # embedded on the trace itself under `feedback_scores`.
        trace = self._request("GET", f"/v1/private/traces/{trace_id}")
        return trace.get("feedback_scores") or []

    def get_spans(self, project: str, trace_id: str, size: int = 10) -> dict:
        """Used to sniff the model id from the first LLM span — handy as experiment metadata."""
        return self._request(
            "GET",
            "/v1/private/spans",
            params={"project_name": project, "trace_id": trace_id, "size": size},
        )

    def update_trace_metadata(
        self, trace_id: str, project: str, metadata: dict
    ) -> None:
        """Patch a trace's metadata. Existing keys not in `metadata` are preserved.

        Use this for any trace-shape normalization your judges need
        (e.g. extracting tool call summaries or flattening span attributes).
        See `references/trace-inspection.md` for the design pattern.
        """
        self._request(
            "PATCH",
            f"/v1/private/traces/{trace_id}",
            json={"project_name": project, "metadata": metadata},
        )

    # --- evaluators (automation rules) ---

    def get_evaluators(self) -> dict:
        """List all automation rule evaluators in the workspace."""
        return self._request(
            "GET", "/v1/private/automations/evaluators", params={"size": 500}
        )

    @staticmethod
    def evaluator_schema_name(ev: dict) -> str:
        """Canonical schema name of an evaluator rule.

        Lives at `code.schema[0].name` in the REST payload; falls back to
        the top-level `name` when absent. This is the string the
        `--evaluator` flag and score-table headers use everywhere.
        """
        schema = (ev.get("code", {}) or {}).get("schema") or [{}]
        return schema[0].get("name") or ev.get("name") or ""

    def list_evaluator_names(self, project: str | None = None) -> list[str]:
        """Schema names of evaluators in the workspace, optionally filtered to one project."""
        evs = self.get_evaluators().get("content", [])
        if project is not None:
            evs = [e for e in evs if e.get("project_name") == project]
        return [n for n in (self.evaluator_schema_name(e) for e in evs) if n]

    def delete_evaluators_by_name(self, names: list[str], project: str) -> int:
        """Delete evaluator rules by schema name. Returns count deleted."""
        evs = self.get_evaluators().get("content", [])
        ids = [
            e["id"] for e in evs
            if e.get("project_name") == project
            and self.evaluator_schema_name(e) in names
        ]
        if not ids:
            return 0
        deleted = 0
        for eid in ids:
            try:
                self._request("DELETE", f"/v1/private/automations/evaluators/{eid}")
                deleted += 1
            except Exception:
                pass
        return deleted

    def create_evaluator(
        self,
        name: str,
        description: str,
        rubric: str,
        project_name: str,
        model: str = "gpt-4o-mini",
    ) -> dict:
        """Create an LLM-as-judge evaluator rule. Idempotent — skips if name already exists."""
        evs = self.get_evaluators().get("content", [])
        project_evs = [e for e in evs if e.get("project_name") == project_name]
        existing_names = [self.evaluator_schema_name(e) for e in project_evs]
        if name in existing_names:
            return {"skipped": True, "name": name}
        project_id = self.get_project_id(project_name)
        # Reuse the model already used in this project rather than defaulting.
        existing_model = model
        if project_evs:
            existing_model = (
                project_evs[0].get("code", {}).get("model", {}).get("name") or model
            )
        body = {
            "name": name,
            "type": "llm_as_judge",
            "project_id": project_id,
            "code": {
                "schema": [
                    {"name": name, "type": "INTEGER", "description": description}
                ],
                "messages": [
                    {"role": "SYSTEM", "content": rubric.strip(), "string_content": True, "structured_content": False},
                    {
                        "role": "USER",
                        "content": (
                            "User message:\n{{input}}\n\n"
                            "Agent response:\n{{output}}\n\n"
                            "tools_called: {{tools_called}}"
                        ),
                        "string_content": True,
                        "structured_content": False,
                    },
                ],
                "model": {"name": existing_model, "temperature": 0.0},
                "variables": {
                    "input": "metadata.user_message",
                    "output": "metadata.assistant_response",
                    "tools_called": "metadata.tools_called",
                    "tool_outputs": "metadata.tool_outputs",
                },
            },
        }
        return self._request("POST", "/v1/private/automations/evaluators", json=body)

    def trigger_evaluation(
        self, project_id: str, trace_ids: list[str], rule_ids: list[str]
    ) -> dict:
        """Fire specific evaluator rules against a set of traces immediately."""
        # Endpoint moved in Opik 2.x — was /automations/evaluators/run.
        return self._request(
            "POST",
            "/v1/private/manual-evaluation/traces",
            json={
                "project_id": project_id,
                "entity_ids": trace_ids,
                "rule_ids": rule_ids,
                "entity_type": "trace",
            },
        )

    # --- datasets ---

    def get_dataset_id(self, name: str) -> str | None:
        """Return the UUID of a dataset by name, or None if it does not exist."""
        data = self._request(
            "GET", "/v1/private/datasets", params={"name": name, "size": 50}
        )
        for d in data.get("content", []):
            if d["name"] == name:
                return d["id"]
        return None

    def create_dataset(
        self,
        name: str,
        description: str | None = None,
        project_name: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Idempotent — returns id of existing dataset if name already taken."""
        existing = self.get_dataset_id(name)
        if existing:
            return existing
        body = {"id": str(uuid7()), "name": name}
        if description:
            body["description"] = description
        if project_name:
            body["project_name"] = project_name
        if tags:
            body["tags"] = tags
        self._request("POST", "/v1/private/datasets", json=body)
        return body["id"]

    def insert_dataset_items(self, dataset_name: str, items: list[dict]) -> None:
        """Upsert items by `id` (caller mints one per item).

        Opik 2.x shape: top-level `id` + `source`; all item fields nested under `data`.
        """
        wrapped = []
        for it in items:
            it = dict(it)
            item_id = it.pop("id", None) or str(uuid7())
            wrapped.append({"id": item_id, "source": "manual", "data": it})
        self._request(
            "PUT",
            "/v1/private/datasets/items",
            json={"dataset_name": dataset_name, "items": wrapped},
        )

    def update_dataset(
        self,
        dataset_id: str,
        name: str,
        description: str | None = None,
        visibility: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Update dataset metadata in place. Opik requires `name` on every update —
        pass the current name if you only want to change description/tags.

        `description` max 255 chars; `visibility` is `private` or `public`.
        Returns 204; no body to parse.
        """
        body: dict = {"name": name}
        if description is not None:
            body["description"] = description
        if visibility is not None:
            body["visibility"] = visibility
        if tags is not None:
            body["tags"] = tags
        self._request("PUT", f"/v1/private/datasets/{dataset_id}", json=body)

    def stream_dataset_items(self, dataset_id: str, max_pages: int = 50) -> list[dict]:
        """Page raw dataset items (no experiment join). Use before any experiment exists."""
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            data = self._request(
                "GET",
                f"/v1/private/datasets/{dataset_id}/items",
                params={"page": page, "size": 100},
            )
            content = data.get("content", [])
            if not content:
                break
            out.extend(content)
            if len(content) < 100:
                break
        return out

    def stream_dataset_items_with_experiment(
        self, dataset_id: str, experiment_id: str, max_pages: int = 50
    ) -> list[dict]:
        """Page items joined with one experiment's outputs/scores. Cap pages to bound cost."""
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            data = self._request(
                "GET",
                f"/v1/private/datasets/{dataset_id}/items/experiments/items",
                params={
                    "experiment_ids": f'["{experiment_id}"]',
                    "page": page,
                    "size": 100,
                },
            )
            content = data.get("content", [])
            if not content:
                break
            out.extend(content)
            if len(content) < 100:
                break
        return out

    # --- experiments ---

    def create_experiment(
        self,
        dataset_name: str,
        name: str,
        experiment_id: str,
        project_id: str,
        description: str | None = None,
        type_: str = "regular",
        status: str = "running",
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Pre-mint `experiment_id` so bulk item endpoint can target it. Body is 201-no-content.

        Opik 2.x `Experiment_Write` has no top-level `description` field —
        we fold it into `metadata.description` so it survives and is
        searchable from the experiment card.
        """
        merged_meta: dict = dict(metadata or {})
        if description:
            merged_meta["description"] = description
        body: dict = {
            "id": experiment_id,
            "dataset_name": dataset_name,
            "name": name,
            "type": type_,
            "status": status,
            "project_id": project_id,
        }
        if merged_meta:
            body["metadata"] = merged_meta
        if tags:
            body["tags"] = tags
        self._request("POST", "/v1/private/experiments", json=body)

    def create_experiment_items(
        self,
        experiment_id: str,
        items: list[dict],
        project_id: str,
        dataset_name: str = "",
        experiment_name: str = "",
    ) -> None:
        """Items carry `dataset_item_id`, `trace_id`, `input`, `output`, `feedback_scores`.

        `project_id` is a contract assertion, not propagated in the body — it
        confirms the caller went through `create_experiment(..., project_id=...)`.
        Without that path, the bulk endpoint silently lazy-creates items into
        Opik's Default Project.
        """
        if not project_id:
            raise ValueError(
                "project_id is required — bulk write without a project-scoped "
                "experiment lazy-creates items into Opik's Default Project."
            )
        # Opik 2.x: PUT (not POST); body requires datasetName + experimentName.
        self._request(
            "PUT",
            "/v1/private/experiments/items/bulk",
            json={
                "experiment_id": experiment_id,
                "dataset_name": dataset_name,
                "experiment_name": experiment_name,
                "items": items,
            },
        )

    def get_experiment(self, experiment_id: str) -> dict:
        """Fetch a single experiment by its UUID."""
        return self._request("GET", f"/v1/private/experiments/{experiment_id}")

    def find_experiment_by_name(self, name: str) -> dict | None:
        """Return the first experiment matching the given name, or None."""
        data = self._request(
            "GET", "/v1/private/experiments", params={"name": name, "size": 50}
        )
        for e in data.get("content", []):
            if e["name"] == name:
                return e
        return None
