"""Opik REST wrapper.

Surface kept narrow on purpose — only the endpoints the EDD scripts use:
- traces: search, batch tag, feedback scores, spans (for run-time model lookup)
- evaluators: list automation rules, trigger manual run
- datasets: resolve id, insert items, page items joined with experiment outputs
- experiments: create (pre-minted id), add items
- optimizations: find, upsert (group experiments under one timeline)
"""

import os
import uuid

import httpx


class OpikClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base = (base_url or os.environ["OPIK_URL"]).rstrip("/")
        self.headers = {"Authorization": api_key or os.environ.get("OPIK_API_KEY", "")}
        # Comet-hosted Opik requires workspace scoping for REST calls; self-hosted ignores it.
        workspace = os.environ.get("OPIK_WORKSPACE")
        if workspace:
            self.headers["Comet-Workspace"] = workspace

    def _request(self, method: str, path: str, **kwargs) -> dict:
        kwargs.setdefault("timeout", 30.0)
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
        (e.g. flattening OpenInference span attributes into trace-level fields).
        See `references/trace-inspection.md` for the design pattern.
        """
        self._request(
            "PATCH",
            f"/v1/private/traces/{trace_id}",
            json={"project_name": project, "metadata": metadata},
        )

    # --- evaluators (automation rules) ---

    def get_evaluators(self) -> dict:
        return self._request(
            "GET", "/v1/private/automations/evaluators", params={"size": 500}
        )

    def trigger_evaluation(
        self, project_id: str, trace_ids: list[str], rule_ids: list[str]
    ) -> dict:
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
        body = {"id": str(uuid.uuid7()), "name": name}
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
            item_id = it.pop("id", None) or str(uuid.uuid7())
            wrapped.append({"id": item_id, "source": "manual", "data": it})
        self._request(
            "PUT",
            "/v1/private/datasets/items",
            json={"dataset_name": dataset_name, "items": wrapped},
        )

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
        optimization_id: str | None = None,
        type_: str = "regular",
        status: str = "running",
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Pre-mint `experiment_id` so bulk item endpoint can target it. Body is 201-no-content."""
        body: dict = {
            "id": experiment_id,
            "dataset_name": dataset_name,
            "name": name,
            "type": type_,
            "status": status,
            "project_id": project_id,
        }
        if optimization_id:
            body["optimization_id"] = optimization_id
        if metadata:
            body["metadata"] = metadata
        if tags:
            body["tags"] = tags
        self._request("POST", "/v1/private/experiments", json=body)

    def create_experiment_items(self, experiment_id: str, items: list[dict]) -> None:
        """Items carry `dataset_item_id`, `trace_id`, `input`, `output`, `feedback_scores`."""
        self._request(
            "POST",
            "/v1/private/experiments/items/bulk",
            json={"experiment_id": experiment_id, "items": items},
        )

    def get_experiment(self, experiment_id: str) -> dict:
        return self._request("GET", f"/v1/private/experiments/{experiment_id}")

    def find_experiment_by_name(self, name: str) -> dict | None:
        data = self._request(
            "GET", "/v1/private/experiments", params={"name": name, "size": 50}
        )
        for e in data.get("content", []):
            if e["name"] == name:
                return e
        return None

    # --- optimizations ---

    def find_optimization(self, name: str, dataset_id: str) -> dict | None:
        data = self._request(
            "GET",
            "/v1/private/optimizations",
            params={"name": name, "dataset_id": dataset_id, "size": 50},
        )
        for o in data.get("content", []):
            if o["name"] == name:
                return o
        return None

    def upsert_optimization(
        self,
        dataset_name: str,
        objective_name: str,
        status: str = "running",
        optimization_id: str | None = None,
        name: str | None = None,
    ) -> str:
        """Returns the optimization id. If optimization_id omitted, server assigns one."""
        body: dict = {
            "dataset_name": dataset_name,
            "objective_name": objective_name,
            "status": status,
        }
        if optimization_id:
            body["id"] = optimization_id
        if name:
            body["name"] = name
        self._request("PUT", "/v1/private/optimizations", json=body)
        return optimization_id or body.get("id", "")
