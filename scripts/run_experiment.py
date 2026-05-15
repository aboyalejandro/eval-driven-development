#!/usr/bin/env python3
"""Run an Opik experiment on top of an existing dataset.

The dataset already carries items linked back to their source traces (built
via `build_dataset.py`). This script triggers a chosen evaluator on those
traces, polls until scores land, then creates an experiment so the score
table is visible in the Opik UI and comparable across runs.

Optional: wrap multiple experiments under an Optimization (same
`--optimization-name`) to get a single timeline view of prompt iterations.

    python run_experiment.py \
        --project my-project \
        --dataset-name edd-recovery-v1 \
        --evaluator "Recovery Persistence" \
        --branch-tag sim-feat/recovery \
        [--experiment-name recovery-pre-merge] \
        [--optimization-name recovery-baseline-vs-v2] \
        [--score-timeout 300] \
        [--dry-run]
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))

from opik_client import OpikClient  # noqa: E402

console = Console()
app = typer.Typer(add_completion=False)


def _find_evaluator(client: OpikClient, project: str, name: str) -> dict | None:
    evals = client.get_evaluators().get("content", [])
    candidates = [ev for ev in evals if ev.get("project_name") == project]
    for ev in candidates:
        schema = (ev.get("code", {}) or {}).get("schema") or [{}]
        if schema[0].get("name") == name or ev.get("name") == name:
            return ev
    return None


def _poll_scores(
    client: OpikClient,
    trace_ids: list[str],
    evaluator: str,
    timeout: int,
) -> dict[str, list[dict]]:
    deadline = time.time() + timeout
    scores: dict[str, list[dict]] = {tid: [] for tid in trace_ids}
    while time.time() < deadline:
        scores = {tid: client.get_trace_scores(tid) for tid in trace_ids}
        done = all(
            any(s.get("name") == evaluator for s in scores[tid]) for tid in trace_ids
        )
        if done:
            return scores
        time.sleep(5)
    return scores


def _resolve_optimization(
    client: OpikClient,
    name: str,
    dataset_id: str,
    dataset_name: str,
    objective: str,
) -> str:
    existing = client.find_optimization(name, dataset_id)
    if existing:
        return existing["id"]
    opt_id = str(uuid.uuid4())
    client.upsert_optimization(
        dataset_name=dataset_name,
        objective_name=objective,
        status="running",
        optimization_id=opt_id,
        name=name,
    )
    return opt_id


def _auto_experiment_name(dataset_name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    sha = uuid.uuid4().hex[:7]
    return f"{dataset_name}-{sha}-{ts}"


@app.command()
def main(
    project: str = typer.Option(..., "--project", help="Opik project name."),
    dataset_name: str = typer.Option(..., "--dataset-name"),
    evaluator: str = typer.Option(
        ..., "--evaluator", help="Schema name of the automation rule (judge)."
    ),
    branch_tag: str = typer.Option(
        ...,
        "--branch-tag",
        help="Trace tag — used for experiment metadata and dataset-item filtering.",
    ),
    experiment_name: str | None = typer.Option(None, "--experiment-name"),
    optimization_name: str | None = typer.Option(
        None,
        "--optimization-name",
        help="If set, experiment is grouped under this optimization timeline.",
    ),
    score_timeout: int = typer.Option(
        300, "--score-timeout", help="Seconds to wait for judge to finish per batch."
    ),
    finalize_optimization: bool = typer.Option(
        False, "--finalize-optimization", help="Mark grouping optimization completed."
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    load_dotenv()
    client = OpikClient()

    dataset_id = client.get_dataset_id(dataset_name)
    if not dataset_id:
        console.print(f"[red]dataset not found: {dataset_name}[/red]")
        raise typer.Exit(code=1)

    judge = _find_evaluator(client, project, evaluator)
    if not judge:
        console.print(
            f"[red]evaluator '{evaluator}' not found in project '{project}'.[/red]\n"
            f"List with: python cli.py check (or your evaluator-listing tool)"
        )
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

    exp_name = experiment_name or _auto_experiment_name(dataset_name)
    plan = {
        "project": project,
        "dataset": dataset_name,
        "dataset_id": dataset_id,
        "evaluator": evaluator,
        "rule_id": judge["id"],
        "traces": len(trace_ids),
        "experiment_name": exp_name,
        "optimization_name": optimization_name,
    }
    console.print(json.dumps(plan, indent=2))
    if dry_run:
        return

    opt_id = None
    if optimization_name:
        opt_id = _resolve_optimization(
            client, optimization_name, dataset_id, dataset_name, evaluator
        )
        console.print(f"optimization id={opt_id}")

    client.trigger_evaluation(project_id, trace_ids, [judge["id"]])
    console.print(f"triggered '{evaluator}' on {len(trace_ids)} traces")

    scores_by_trace = _poll_scores(client, trace_ids, evaluator, score_timeout)
    landed = sum(
        1
        for tid in trace_ids
        if any(s.get("name") == evaluator for s in scores_by_trace.get(tid, []))
    )
    console.print(f"scored: {landed}/{len(trace_ids)}")

    metadata: dict[str, Any] = {
        "evaluators": [evaluator],
        "source": "eval-driven-development",
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

    exp_id = str(uuid.uuid4())
    client.create_experiment(
        dataset_name=dataset_name,
        name=exp_name,
        experiment_id=exp_id,
        project_id=project_id,
        optimization_id=opt_id,
        metadata=metadata,
        tags=[branch_tag],
    )
    bulk_items = [
        {
            "id": str(uuid.uuid4()),
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
    client.create_experiment_items(exp_id, bulk_items)
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

    base = os.environ.get("OPIK_URL", "").rstrip("/")
    if base:
        console.print(f"  {base}/experiments/{exp_id}")
        if opt_id:
            console.print(f"  {base}/optimizations/{opt_id}")

    print(json.dumps({"experiment_id": exp_id, "optimization_id": opt_id}))


if __name__ == "__main__":
    app()
