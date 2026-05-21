#!/usr/bin/env python3
"""edd-build — sim traces → Opik dataset. See scripts/simulation/CLAUDE.md."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console

from shared.opik_client import OpikClient
from shared.session import branch_tag_warning, session_tags
from shared.settings import settings

console = Console()
app = typer.Typer(add_completion=False)


def _default_extractor(trace: dict) -> dict | None:
    """Read the enrichment-normalized convention from `trace.metadata`.

    `_local/enrich_traces_<sdk>.py` patches `metadata.user_message` and
    `metadata.assistant_response` via `OpikClient.update_trace_metadata`.
    The default extractor reads from the same place — same source of truth
    as the judges (which read `metadata.*` variables). If neither
    enrichment nor a custom `--extractor` is wired, `--dry-run` reports
    zero items. See `references/trace-enrichment.md`.
    """
    meta = trace.get("metadata") or {}
    if not isinstance(meta, dict):
        return None
    user_message = meta.get("user_message", "")
    assistant_response = meta.get("assistant_response", "")
    if not user_message or not assistant_response:
        return None
    item: dict[str, Any] = {
        "user_message": user_message,
        "assistant_response": assistant_response,
    }
    if meta:
        item["trace_metadata"] = meta
    return item


def _default_drop_reason(trace: dict) -> str:
    """Surface why `_default_extractor` returned None for this trace."""
    meta = trace.get("metadata")
    if meta is None:
        return "metadata missing"
    if not isinstance(meta, dict):
        return f"metadata is {type(meta).__name__}, expected dict"
    if not meta.get("user_message"):
        return "metadata.user_message missing/empty — did enrichment run?"
    if not meta.get("assistant_response"):
        return "metadata.assistant_response missing/empty — did enrichment run?"
    return "unknown"


def _load_extractor(spec: str | None) -> Callable[[dict], dict | None]:
    if not spec:
        return _default_extractor
    if ":" not in spec:
        raise typer.BadParameter("--extractor must be 'module.path:function'")
    mod_path, func = spec.split(":", 1)
    # Prepend CWD so callers can reference modules relative to where they run
    # the script (e.g. `_local.openinference_extractor` from repo root).
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    module = importlib.import_module(mod_path)
    return getattr(module, func)


def _parse_from(value: str | None, default_hours: int = 24) -> str:
    """Return an ISO-8601 lower-bound timestamp, defaulting to N hours ago.

    Default raised from 6h → 24h so re-runs minutes apart don't silently drop
    the earliest traces when wall-clock slides past their start_time.
    """
    if not value:
        return (datetime.now(timezone.utc) - timedelta(hours=default_hours)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
    # accept ISO-8601 already
    if value.endswith("Z"):
        return value
    return value


def _filter_traces(traces: list[dict], branch_tag: str) -> list[dict]:
    return [t for t in traces if branch_tag in (t.get("tags") or [])]


@app.command()
def main(
    project: str = typer.Option(..., "--project", help="Opik project name."),
    dataset_name: str = typer.Option(
        ..., "--dataset-name", help="Destination dataset. Created if missing."
    ),
    branch_tag: str = typer.Option(
        ...,
        "--branch-tag",
        help="Trace tag to filter on — branch name = topic = tag (set by `edd run`).",
    ),
    from_time: str | None = typer.Option(
        None,
        "--from",
        help="ISO time lower bound. Defaults to 24h ago.",
    ),
    extractor: str | None = typer.Option(
        None,
        "--extractor",
        help="Dotted path `module:function` returning an item dict (or None) per trace.",
    ),
    description: str = typer.Option(
        ...,
        "--description",
        help="Required. Short summary of what this dataset captures (e.g. the topic + hypothesis).",
    ),
    extra_tag: list[str] = typer.Option(
        [],
        "--tag",
        help="Extra tag to attach to the dataset. Repeatable. Stacks on top of branch-tag + session tags.",
    ),
    allow_main: bool = typer.Option(
        False,
        "--allow-main",
        help="Silence the warning when --branch-tag references main/master.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Build an Opik dataset from sim traces tagged by edd run."""
    if not allow_main and (w := branch_tag_warning(branch_tag)):
        console.print(f"[yellow]{w}[/yellow]")
    extractor_fn = _load_extractor(extractor)
    from_iso = _parse_from(from_time)

    client = OpikClient()
    traces = client.search_traces(project, from_time=from_iso)
    matched = _filter_traces(traces, branch_tag)
    console.print(
        f"[bold]{len(matched)}[/bold] traces match tag={branch_tag} "
        f"from={from_iso} (of {len(traces)} scanned)"
    )
    if not matched:
        # Differentiate: empty window vs window has traces but none with our tag.
        if not traces:
            console.print(f"[yellow]no traces in window since {from_iso}[/yellow]")
            console.print(
                "[yellow]hint: --from may be set after edd run; widen it, "
                "or re-run edd run if the batch is stale[/yellow]"
            )
        else:
            found_tags = sorted({tag for t in traces for tag in (t.get("tags") or [])})
            console.print(
                f"[yellow]{len(traces)} traces in window but none tagged "
                f"`{branch_tag}`[/yellow]"
            )
            console.print(f"[yellow]tags actually present: {found_tags}[/yellow]")
            console.print(
                "[yellow]hint: confirm `branch_tag` in .edd/session.json matches "
                "what edd run stamped, or re-run edd run[/yellow]"
            )
        raise typer.Exit(code=1)

    items: list[dict] = []
    drop_reasons: list[tuple[str, str]] = []
    is_default_extractor = extractor is None
    for tr in matched:
        item = extractor_fn(tr)
        if not item:
            reason = (
                _default_drop_reason(tr)
                if is_default_extractor
                else "custom extractor returned None"
            )
            drop_reasons.append((tr["id"], reason))
            continue
        item["id"] = tr["id"]  # stable: same trace → same item id → idempotent upsert
        items.append(item)
    console.print(f"extracted {len(items)} items, dropped {len(drop_reasons)}")
    for trace_id, reason in drop_reasons:
        console.print(f"[yellow]  dropped {trace_id}: {reason}[/yellow]")

    if dry_run:
        sample = items[:2]
        console.print(json.dumps(sample, indent=2, default=str))
        return

    dataset_tags = [branch_tag, *session_tags(), *extra_tag]
    client.create_dataset(
        dataset_name,
        description=description,
        project_name=project,
        tags=dataset_tags,
    )
    client.insert_dataset_items(dataset_name, items)
    dataset_id = client.get_dataset_id(dataset_name)
    base = settings.opik_url.rstrip("/")
    console.print(
        f"[green]wrote {len(items)} items[/green] → dataset={dataset_name} (id={dataset_id})"
    )
    if base:
        console.print(f"  {base}/datasets/{dataset_id}")


if __name__ == "__main__":
    app()
