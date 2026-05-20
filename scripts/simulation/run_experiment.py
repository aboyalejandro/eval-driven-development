#!/usr/bin/env python3
"""edd-run — dataset → experiment with judge scores. See scripts/simulation/CLAUDE.md."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import typer
from fastuuid import uuid7
from rich.console import Console

from shared.opik_client import OpikClient
from shared.session import branch_tag_warning, session_tags
from shared.settings import settings
from setup.results import _latest_per_judge


def _commit_items_with_retry(
    client: OpikClient,
    exp_id: str,
    bulk_items: list[dict],
    *,
    project_id: str,
    dataset_name: str,
    experiment_name: str,
    max_attempts: int = 3,
) -> None:
    """Retry the bulk items write on transient 5xx (observed flaky on Opik).

    Judge firing is the expensive step; this commit is cheap to retry and
    must not re-trigger judges. Raises after `max_attempts` 5xx in a row.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            client.create_experiment_items(
                exp_id,
                bulk_items,
                project_id=project_id,
                dataset_name=dataset_name,
                experiment_name=experiment_name,
            )
            return
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500 or attempt == max_attempts:
                raise
            wait = 2**attempt
            console.print(
                f"[yellow]commit items attempt {attempt}/{max_attempts} got "
                f"{e.response.status_code}; retrying in {wait}s[/yellow]"
            )
            time.sleep(wait)


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
    extra_tag: list[str] = typer.Option(
        [],
        "--tag",
        help="Extra tag for the experiment. Repeatable. Stacks on top of branch-tag + session tags.",
    ),
    score_timeout: int = typer.Option(
        300, "--score-timeout", help="Seconds to wait for judge to finish per batch."
    ),
    resume_experiment: str | None = typer.Option(
        None,
        "--resume-experiment",
        help=(
            "Experiment id from a previous run that scored successfully but "
            "failed at the items-write step. Skips judge firing + experiment "
            "creation and only writes the items, reading scores already on "
            "the traces."
        ),
    ),
    score_before: str | None = typer.Option(
        None,
        "--score-before",
        help=(
            "ISO timestamp upper bound for resume mode. Required when judges "
            "may have been re-fired between the original failure and the "
            "resume — pins score selection to the original window so newer "
            "scores from unrelated runs don't get attached to this experiment. "
            "Pass the line `triggered_after` from the original log."
        ),
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

    def _tid(it: dict) -> str | None:
        d = it.get("data") or it
        return d.get("source_trace_id") or it.get("id")

    items = list(client.stream_dataset_items(dataset_id))
    trace_ids = [_tid(it) for it in items]
    trace_ids = [t for t in trace_ids if t]
    if not trace_ids:
        console.print("[red]no trace id on dataset items — rebuild dataset.[/red]")
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
    }
    console.print(json.dumps(plan, indent=2))
    if dry_run:
        return

    shared_tags = [branch_tag, *session_tags(), *extra_tag]

    if resume_experiment:
        # Resume path: judges already scored, experiment row already created;
        # only the items-write failed. Read scores back from the traces.
        # `score_before` upper-bounds score selection so a re-fire of judges
        # between the original failure and the resume can't attach unrelated
        # newer scores to this experiment.
        exp_id = resume_experiment
        console.print(
            f"[yellow]resuming experiment {exp_id} — skipping judge fire + "
            "create_experiment[/yellow]"
        )
        if not score_before:
            console.print(
                "[yellow]--score-before not set; including the most recent "
                "score per judge with no upper bound. If judges have been "
                "re-fired since the original failure, pass --score-before "
                "<original triggered_after> to scope back.[/yellow]"
            )

        def _select(tid: str) -> list[dict]:
            scores = client.get_trace_scores(tid)
            if score_before:
                scores = [s for s in scores if s.get("created_at", "") <= score_before]
            return _latest_per_judge(scores)

        scores_by_trace = {tid: _select(tid) for tid in trace_ids}
        landed = sum(
            1
            for tid in trace_ids
            if any(s.get("name") in found_names for s in scores_by_trace.get(tid, []))
        )
        console.print(f"resumed scores: {landed}/{len(trace_ids)}")
    else:
        triggered_after = datetime.now(timezone.utc).isoformat()
        client.trigger_evaluation(project_id, trace_ids, [j["id"] for j in judges])
        console.print(
            f"triggered {len(judges)} judges on {len(trace_ids)} traces "
            f"(triggered_after={triggered_after})"
        )
        console.print(
            f"[dim]if items-write fails, recover with: "
            f"edd-run ... --resume-experiment <id> --score-before {triggered_after}[/dim]"
        )

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
        sample_tid = trace_ids[0]
        spans = client.get_spans(project, sample_tid, size=10).get("content", [])
        for sp in spans:
            if sp.get("type") == "llm" and sp.get("model"):
                metadata["model"] = sp["model"]
                break

        exp_id = str(uuid7())
        client.create_experiment(
            dataset_name=dataset_name,
            name=exp_name,
            experiment_id=exp_id,
            project_id=project_id,
            description=description,
            metadata=metadata,
            tags=shared_tags,
        )
    bulk_items = [
        {
            "id": str(uuid7()),
            "experiment_id": exp_id,
            "dataset_item_id": it.get("id"),
            "trace_id": _tid(it),
            "input": {"message": (it.get("data") or it).get("user_message", "")},
            "output": {"output": (it.get("data") or it).get("assistant_response", "")},
            "metadata": {
                k: ((it.get("data") or it).get("trace_metadata") or {}).get(k, "")
                for k in ("tools_called", "tool_outputs")
            },
            "feedback_scores": scores_by_trace.get(_tid(it), []),
        }
        for it in items
        if _tid(it)
    ]
    try:
        _commit_items_with_retry(
            client,
            exp_id,
            bulk_items,
            project_id=project_id,
            dataset_name=dataset_name,
            experiment_name=exp_name,
        )
    except httpx.HTTPStatusError as e:
        console.print(
            f"[red]commit items failed after retries: {e.response.status_code}[/red]"
        )
        console.print(
            f"[yellow]experiment row exists at id={exp_id}; rerun with "
            f"`--resume-experiment {exp_id}` once Opik recovers[/yellow]"
        )
        raise typer.Exit(code=1)
    console.print(f"[green]experiment {exp_name}[/green] (id={exp_id})")

    base = settings.opik_url.rstrip("/")
    if base:
        console.print(f"  {base}/experiments/{exp_id}")

    # Machine-readable output — pipe with jq to extract experiment_id.
    print(json.dumps({"experiment_id": exp_id}))


if __name__ == "__main__":
    app()
