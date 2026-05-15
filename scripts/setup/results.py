"""Poll trace store for judge scores, render per-dimension table."""

import time

from rich.console import Console
from rich.table import Table

from shared.opik_client import OpikClient

console = Console()


def poll_scores(
    client: OpikClient,
    trace_ids: list[str],
    timeout: int = 120,
    expected: set[str] | None = None,
) -> dict[str, list[dict]]:
    """Poll until each trace has scores from every expected judge, or timeout.

    Returns {trace_id: [score_dict, ...]}.
    """
    deadline = time.time() + timeout
    scored: dict[str, list[dict]] = {}

    while time.time() < deadline:
        scored = {tid: client.get_trace_scores(tid) for tid in trace_ids}
        if expected:
            done = all(
                {s["name"] for s in scored[tid]} >= expected for tid in trace_ids
            )
        else:
            done = all(scored[tid] for tid in trace_ids)
        if done:
            break
        time.sleep(5)

    return scored


def print_results(scored: dict[str, list[dict]]) -> bool:
    """Render scores. Returns True if no judge scored < 0.5."""
    if not scored:
        console.print("[red]no scores[/red]")
        return False

    judges = sorted({s["name"] for scores in scored.values() for s in scores})
    table = Table(title="Eval results")
    table.add_column("Trace")
    for j in judges:
        table.add_column(j, justify="right")

    all_pass = True
    for tid, scores in scored.items():
        by_name = {s["name"]: s["value"] for s in scores}
        row = [tid[:8]]
        for j in judges:
            v = by_name.get(j)
            if v is None:
                row.append("[dim]-[/dim]")
            elif v < 0.5:
                row.append(f"[red]{v:.2f}[/red]")
                all_pass = False
            else:
                row.append(f"{v:.2f}")
        table.add_row(*row)

    console.print(table)

    # For each red cell, print the judge's reason inline so you don't need
    # to open the Opik UI to understand what failed.
    failures = [
        (tid[:8], s["name"], s["value"], s.get("reason", ""))
        for tid, scores in scored.items()
        for s in scores
        if s["value"] < 0.5 and s.get("reason")
    ]
    if failures:
        console.print()
        for tid, name, val, reason in failures:
            console.print(
                f"  [red]{tid} {name}={val:.2f}[/red]  {reason[:200]}"
            )

    return all_pass
