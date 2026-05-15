"""Poll trace store for judge scores, render per-dimension table."""

import time

from rich.console import Console
from rich.table import Table

from shared.opik_client import OpikClient

console = Console()


def _latest_per_judge(scores: list[dict]) -> list[dict]:
    """One score per judge name — the most recently created wins.

    Prevents stale pre-enrichment scores from overriding fresh post-enrichment
    scores when the same evaluator is triggered twice on the same trace.
    """
    latest: dict[str, dict] = {}
    for s in scores:
        name = s.get("name", "")
        existing = latest.get(name)
        if not existing or s.get("created_at", "") > existing.get("created_at", ""):
            latest[name] = s
    return list(latest.values())


def poll_scores(
    client: OpikClient,
    trace_ids: list[str],
    timeout: int = 120,
    expected: set[str] | None = None,
    triggered_after: str | None = None,
) -> dict[str, list[dict]]:
    """Poll until each trace has fresh scores from every expected judge.

    triggered_after: ISO timestamp recorded just before trigger_evaluation().
    When set, the poll only counts scores with created_at >= triggered_after,
    preventing stale pre-existing scores from causing an early exit before the
    new trigger's results land (e.g. when judges are fired twice: once before
    enrichment and once after).
    """
    # Brief initial pause — lets Opik queue and begin processing the new
    # trigger before we start reading, avoiding an immediate hit on old scores.
    if triggered_after:
        time.sleep(12)

    deadline = time.time() + timeout
    scored: dict[str, list[dict]] = {}

    while time.time() < deadline:
        raw = {tid: client.get_trace_scores(tid) for tid in trace_ids}
        # Deduplicate per judge (latest created_at wins).
        scored = {tid: _latest_per_judge(v) for tid, v in raw.items()}

        if expected:
            if triggered_after:
                done = all(
                    {s["name"] for s in scored[tid]
                     if s.get("created_at", "") >= triggered_after} >= expected
                    for tid in trace_ids
                )
            else:
                done = all(
                    {s["name"] for s in scored[tid]} >= expected
                    for tid in trace_ids
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
