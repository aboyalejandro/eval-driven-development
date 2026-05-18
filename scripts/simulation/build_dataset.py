#!/usr/bin/env python3
"""edd-build — sim traces → Opik dataset. See scripts/simulation/CLAUDE.md."""

import importlib
import json
import sys
import uuid
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


def _parse_from(value: str | None, default_hours: int = 6) -> str:
    """Return an ISO-8601 lower-bound timestamp, defaulting to N hours ago."""
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
        help="Trace tag to filter on. Set by cli.py as `sim-<branch>`.",
    ),
    from_time: str | None = typer.Option(
        None,
        "--from",
        help="ISO time lower bound. Defaults to 6h ago.",
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
        # Help diagnose: show what tags actually exist in the window.
        found_tags = sorted({tag for t in traces for tag in (t.get("tags") or [])})
        if found_tags:
            console.print(f"[yellow]tags found in window: {found_tags}[/yellow]")
            console.print(
                "[yellow]hint: re-run cli.py run to re-tag, or widen --from[/yellow]"
            )
        else:
            console.print("[yellow]no tags found on any trace in this window[/yellow]")
            console.print(
                "[yellow]hint: cli.py run may not have tagged traces — check batch_update_traces[/yellow]"
            )
        raise typer.Exit(code=1)

    items: list[dict] = []
    dropped = 0
    for tr in matched:
        item = extractor_fn(tr)
        if not item:
            dropped += 1
            continue
        item.setdefault("id", str(uuid.uuid7()))
        item["source_trace_id"] = tr["id"]
        items.append(item)
    console.print(f"extracted {len(items)} items, dropped {dropped}")

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
