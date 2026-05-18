#!/usr/bin/env python3
"""edd-run — dataset → experiment, optionally under an optimization. See scripts/simulation/CLAUDE.md."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import typer
from rich.console import Console

from shared.opik_client import OpikClient
from shared.session import branch_tag_warning, session_tags
from shared.settings import settings
from setup.results import _latest_per_judge

console = Console()
app = typer.Typer(add_completion=False)


def _find_evaluators(client: OpikClient, project: str, names: list[str]) -> list[dict]:
    """Return evaluator dicts for the given schema names, warning on any not found."""
    evals = client.get_evaluators().get("content", [])
    candidates = [ev for ev in evals if ev.get("project_name") == project]
    found = []
    for name in names:
        for ev in candidates:
            if client.evaluator_schema_name(ev) == name:
                found.append(ev)
                break
        else:
            console.print(f"[yellow]evaluator not found: {name}[/yellow]")
    return found


def _poll_scores(
    client: OpikClient,
    trace_ids: list[str],
    evaluator_names: set[str],
    timeout: int,
    triggered_after: str | None = None,
) -> dict[str, list[dict]]:
    """Same triggered_after logic as setup.results.poll_scores — prevents
    stale pre-enrichment scores from masking the fresh experiment trigger."""
    if triggered_after:
        time.sleep(12)
    deadline = time.time() + timeout
    scores: dict[str, list[dict]] = {tid: [] for tid in trace_ids}
    while time.time() < deadline:
        raw = {tid: client.get_trace_scores(tid) for tid in trace_ids}
        scores = {tid: _latest_per_judge(v) for tid, v in raw.items()}
        if triggered_after:
            landed = {
                s.get("name")
                for tid in trace_ids
                for s in scores[tid]
                if s.get("created_at", "") >= triggered_after
            }
        else:
            landed = {s.get("name") for tid in trace_ids for s in scores[tid]}
        if evaluator_names <= landed:
            return scores
        time.sleep(5)
    return scores


def _resolve_optimization(
    client: OpikClient,
    name: str,
    dataset_id: str,
    dataset_name: str,
    objective: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Find or create an optimization group, returning its id."""
    existing = client.find_optimization(name, dataset_id)
    if existing:
        return existing["id"]
    opt_id = str(uuid.uuid7())
    client.upsert_optimization(
        dataset_name=dataset_name,
        objective_name=objective,
        status="running",
        optimization_id=opt_id,
        name=name,
        description=description,
        tags=tags,
    )
    return opt_id


def _auto_experiment_name(dataset_name: str) -> str:
    """Generate a unique experiment name from dataset name + timestamp + short hash."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    sha = uuid.uuid4().hex[:7]
    return f"{dataset_name}-{sha}-{ts}"


@app.command()
def main(
    project: str = typer.Option(..., "--project", help="Opik project name."),
    dataset_name: str = typer.Option(..., "--dataset-name"),
    evaluator: str = typer.Option(
        ..., "--evaluator", help="Comma-separated schema names of judges to run."
    ),
    branch_tag: str = typer.Option(
        ...,
        "--branch-tag",
        help="Trace tag — used for experiment metadata and dataset-item filtering.",
    ),
    experiment_name: str | None = typer.Option(None, "--experiment-name"),
    description: str = typer.Option(
        ...,
        "--description",
        help="Required. Short summary of this experiment (hypothesis + what changed).",
    ),
    optimization_name: str | None = typer.Option(
        None,
        "--optimization-name",
        help="If set, experiment is grouped under this optimization timeline.",
    ),
    optimization_description: str | None = typer.Option(
        None,
        "--optimization-description",
        help="Description applied when the optimization is first created. Reused for baseline + later variants.",
    ),
    extra_tag: list[str] = typer.Option(
        [],
        "--tag",
        help="Extra tag for experiment + optimization. Repeatable. Stacks on top of branch-tag + session tags.",
    ),
    score_timeout: int = typer.Option(
        300, "--score-timeout", help="Seconds to wait for judge to finish per batch."
    ),
    finalize_optimization: bool = typer.Option(
        False, "--finalize-optimization", help="Mark grouping optimization completed."
    ),
    allow_main: bool = typer.Option(
        False,
        "--allow-main",
        help="Silence the warning when --branch-tag references main/master.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    if not allow_main and (w := branch_tag_warning(branch_tag)):
        console.print(f"[yellow]{w}[/yellow]")
    client = OpikClient()

    dataset_id = client.get_dataset_id(dataset_name)
    if not dataset_id:
        console.print(f"[red]dataset not found: {dataset_name}[/red]")
        raise typer.Exit(code=1)

    evaluator_names = [n.strip() for n in evaluator.split(",")]
    judges = _find_evaluators(client, project, evaluator_names)
    if not judges:
        console.print(f"[red]no evaluators found in project '{project}'.[/red]")
        raise typer.Exit(code=1)

    project_id = client.get_project_id(project)

    items = client.stream_dataset_items(dataset_id)
    trace_ids = [(it.get("data") or it).get("source_trace_id") for it in items]
    trace_ids = [t for t in trace_ids if t]
    if not trace_ids:
        console.print(
            "[red]no source_trace_id on dataset items — rebuild dataset.[/red]"
        )
        raise typer.Exit(code=1)

    found_names = [client.evaluator_schema_name(j) for j in judges]
    exp_name = experiment_name or _auto_experiment_name(dataset_name)
    plan = {
        "project": project,
        "dataset": dataset_name,
        "dataset_id": dataset_id,
        "evaluators": found_names,
        "traces": len(trace_ids),
        "experiment_name": exp_name,
        "optimization_name": optimization_name,
    }
    console.print(json.dumps(plan, indent=2))
    if dry_run:
        return

    shared_tags = [branch_tag, *session_tags(), *extra_tag]
    opt_id = None
    if optimization_name:
        opt_id = _resolve_optimization(
            client,
            optimization_name,
            dataset_id,
            dataset_name,
            found_names[0],
            description=optimization_description,
            tags=shared_tags,
        )
        console.print(f"optimization id={opt_id}")

    triggered_after = datetime.now(timezone.utc).isoformat()
    client.trigger_evaluation(project_id, trace_ids, [j["id"] for j in judges])
    console.print(f"triggered {len(judges)} judges on {len(trace_ids)} traces")

    scores_by_trace = _poll_scores(
        client, trace_ids, set(found_names), score_timeout, triggered_after
    )
    landed = sum(
        1
        for tid in trace_ids
        if any(s.get("name") in found_names for s in scores_by_trace.get(tid, []))
    )
    console.print(f"scored: {landed}/{len(trace_ids)}")

    metadata: dict[str, Any] = {
        "evaluators": found_names,
        "source": "edd",
        "branch": branch_tag,
    }
    if opt_id:
        metadata["optimization_id"] = opt_id
    sample_tid = trace_ids[0]
    spans = client.get_spans(project, sample_tid, size=10).get("content", [])
    for sp in spans:
        if sp.get("type") == "llm" and sp.get("model"):
            metadata["model"] = sp["model"]
            break

    exp_id = str(uuid.uuid7())
    client.create_experiment(
        dataset_name=dataset_name,
        name=exp_name,
        experiment_id=exp_id,
        project_id=project_id,
        description=description,
        optimization_id=opt_id,
        metadata=metadata,
        tags=shared_tags,
    )
    bulk_items = [
        {
            "id": str(uuid.uuid7()),
            "experiment_id": exp_id,
            "dataset_item_id": (it.get("data") or it).get("id") or it.get("id"),
            "trace_id": (it.get("data") or it).get("source_trace_id"),
            "input": {"user_message": (it.get("data") or it).get("user_message", "")},
            "output": {
                "assistant_response": (it.get("data") or it).get(
                    "assistant_response", ""
                )
            },
            "feedback_scores": scores_by_trace.get(
                (it.get("data") or it).get("source_trace_id"), []
            ),
        }
        for it in items
        if (it.get("data") or it).get("source_trace_id")
    ]
    client.create_experiment_items(
        exp_id, bulk_items, dataset_name=dataset_name, experiment_name=exp_name
    )
    console.print(f"[green]experiment {exp_name}[/green] (id={exp_id})")

    if finalize_optimization and opt_id:
        client.upsert_optimization(
            dataset_name=dataset_name,
            objective_name=evaluator,
            status="completed",
            optimization_id=opt_id,
            name=optimization_name,
        )
        console.print(f"optimization {opt_id} marked completed")

    base = settings.opik_url.rstrip("/")
    if base:
        console.print(f"  {base}/experiments/{exp_id}")
        if opt_id:
            console.print(f"  {base}/optimizations/{opt_id}")

    # Machine-readable output — pipe with jq to extract experiment_id / optimization_id.
    print(json.dumps({"experiment_id": exp_id, "optimization_id": opt_id}))


if __name__ == "__main__":
    app()
