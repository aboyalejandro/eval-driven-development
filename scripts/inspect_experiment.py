#!/usr/bin/env python3
"""Inspect experiment results — per-evaluator aggregate + failure surface.

Joins dataset items to experiment outputs and feedback scores, prints a
digest table, and lists items where any judge scored below `--score-threshold`.

    python inspect_experiment.py --experiment-id <uuid>
    python inspect_experiment.py --experiment-name <name> --score-threshold 0.5
"""

import json
import os
import sys
from pathlib import Path
from statistics import mean

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))

from opik_client import OpikClient  # noqa: E402

console = Console()
app = typer.Typer(add_completion=False)


def _resolve_experiment(
    client: OpikClient, exp_id: str | None, exp_name: str | None
) -> dict:
    if exp_id:
        return client.get_experiment(exp_id)
    if exp_name:
        found = client.find_experiment_by_name(exp_name)
        if found:
            return found
    raise typer.BadParameter("provide --experiment-id or --experiment-name")


def _aggregate(items: list[dict], evaluator: str | None) -> dict[str, dict]:
    by_eval: dict[str, list[float]] = {}
    for it in items:
        scores = it.get("feedback_scores") or []
        for s in scores:
            name = s.get("name")
            if evaluator and name != evaluator:
                continue
            by_eval.setdefault(name, []).append(float(s.get("value", 0)))
    return {
        name: {
            "n": len(vals),
            "avg": mean(vals) if vals else 0.0,
            "min": min(vals) if vals else 0.0,
            "max": max(vals) if vals else 0.0,
        }
        for name, vals in by_eval.items()
    }


def _print_digest(agg: dict[str, dict]) -> None:
    table = Table(title="Per-evaluator digest")
    table.add_column("Evaluator")
    table.add_column("N", justify="right")
    table.add_column("Avg", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    for name, stats in sorted(agg.items()):
        table.add_row(
            name,
            str(stats["n"]),
            f"{stats['avg']:.2f}",
            f"{stats['min']:.2f}",
            f"{stats['max']:.2f}",
        )
    console.print(table)


def _print_failures(
    items: list[dict], threshold: float, evaluator: str | None, limit: int
) -> None:
    fails = []
    for it in items:
        scores = it.get("feedback_scores") or []
        for s in scores:
            name = s.get("name")
            if evaluator and name != evaluator:
                continue
            if float(s.get("value", 1.0)) < threshold:
                fails.append((it, name, float(s["value"])))
                break
    console.print(
        f"[bold]{len(fails)}[/bold] failures below {threshold} "
        f"(showing first {min(limit, len(fails))})"
    )
    base = os.environ.get("OPIK_URL", "").rstrip("/")
    for it, name, val in fails[:limit]:
        data = it.get("data") or it
        msg = (data.get("user_message") or "")[:120].replace("\n", " ")
        resp = (data.get("assistant_response") or "")[:160].replace("\n", " ")
        tid = it.get("trace_id") or data.get("source_trace_id")
        console.print(
            f"  [red]{name}={val:.2f}[/red]  user={msg!r}\n"
            f"    -> {resp!r}\n"
            f"    trace={base}/traces/{tid}"
            if base
            else f"    trace={tid}"
        )


@app.command()
def main(
    experiment_id: str | None = typer.Option(None, "--experiment-id"),
    experiment_name: str | None = typer.Option(None, "--experiment-name"),
    score_threshold: float = typer.Option(0.5, "--score-threshold"),
    evaluator: str | None = typer.Option(
        None, "--evaluator", help="Filter to one judge — others still aggregated."
    ),
    fail_limit: int = typer.Option(20, "--fail-limit"),
    out_jsonl: Path | None = typer.Option(
        None, "--out-jsonl", help="Dump joined items to JSONL."
    ),
):
    load_dotenv()
    client = OpikClient()
    exp = _resolve_experiment(client, experiment_id, experiment_name)
    exp_id = exp["id"]
    dataset_id = exp.get("dataset_id")
    if not dataset_id:
        console.print("[red]experiment missing dataset_id[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"inspecting [bold]{exp.get('name')}[/bold] ({exp_id}) dataset={dataset_id}"
    )
    items = client.stream_dataset_items_with_experiment(dataset_id, exp_id)
    console.print(f"loaded {len(items)} joined items")
    agg = _aggregate(items, evaluator)
    _print_digest(agg)
    _print_failures(items, score_threshold, evaluator, fail_limit)
    if out_jsonl:
        out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with out_jsonl.open("w") as f:
            for it in items:
                f.write(json.dumps(it) + "\n")
        console.print(f"wrote {len(items)} items → {out_jsonl}")


if __name__ == "__main__":
    app()
