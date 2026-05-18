#!/usr/bin/env python3
"""edd — inner-loop CLI: run, score, check. See scripts/setup/CLAUDE.md."""

import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console

from setup.agent import run_scenario
from setup.results import poll_scores, print_results
from shared.opik_client import OpikClient
from shared.settings import settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

app = typer.Typer()
console = Console()
DEFAULT_PROJECT = settings.eval_project


def _load_scenarios(arg: str) -> list[dict]:
    """File path → list of scenario dicts. Else single message → one scenario.

    File format: one scenario per line. Plain message OR JSON object with
    optional `context`, `followups`, `evaluators` fields.
    """
    p = Path(arg)
    if not p.exists():
        return [{"message": arg}]
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(json.loads(line) if line.startswith("{") else {"message": line})
    return out


def _git_branch() -> str | None:
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() or None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


@app.command()
def run(
    message_or_file: str,
    project: str = typer.Option(DEFAULT_PROJECT, "--project"),
    wait: bool = typer.Option(False, "--wait", "-w"),
    timeout: int = typer.Option(120),
    evaluators: str = typer.Option(
        None,
        "--evaluators",
        "-e",
        help="Comma-separated judge names. Unions with per-scenario `evaluators` field.",
    ),
):
    """Run a message or a scenarios file."""
    scenarios = _load_scenarios(message_or_file)
    flag_targets = {n.strip() for n in evaluators.split(",")} if evaluators else set()
    asyncio.run(_run(scenarios, project, wait, timeout, flag_targets))


async def _run(
    scenarios: list[dict],
    project: str,
    wait: bool,
    timeout: int,
    flag_targets: set[str],
) -> None:
    """Emit scenarios, tag traces, optionally trigger judges and poll scores."""
    # The agent under test owns its own OTEL → Opik tracing (see PREREQUISITES.md).
    # This process is just an HTTP client; we don't instrument it.

    run_id = uuid.uuid4().hex[:8]
    start = datetime.now(timezone.utc)

    # 2. Run scenarios.
    for i, sc in enumerate(scenarios):
        log.info("[%d/%d] %s", i + 1, len(scenarios), sc["message"][:80])
        await run_scenario(
            message=sc["message"],
            run_id=run_id,
            context=sc.get("context"),
            followups=sc.get("followups"),
        )

    # 3. Flush — judges can't score a trace that hasn't landed.
    log.info("flushing traces...")
    time.sleep(3)

    # 4. Find this run's traces. With external HTTP agents the trace name is
    # set by the agent runtime (not by us), so name-prefix filtering doesn't
    # work — we rely on the time window + dedicated project (see PREREQUISITES).
    client = OpikClient()
    from_time = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    traces = client.search_traces(project, from_time=from_time)
    trace_ids = [t["id"] for t in traces]
    if not trace_ids:
        console.print("[red]no traces found — verify agent is emitting to Opik[/red]")
        raise typer.Exit(1)
    expected = sum(1 + len(sc.get("followups") or []) for sc in scenarios)
    if len(trace_ids) != expected:
        log.warning(
            "trace count mismatch: expected %d, got %d (concurrent traffic in project?)",
            expected,
            len(trace_ids),
        )
    log.info("found %d traces", len(trace_ids))

    # 5. Tag with branch + run_id for cross-branch comparison in the Opik UI.
    branch = _git_branch()
    tags = [f"run-{run_id}"]
    if branch:
        tags.append(f"sim-{branch}")
    client.batch_update_traces(trace_ids, project, tags_to_add=tags)
    log.info("tagged: %s", ", ".join(tags))

    # If your judges need trace-shape normalization (tool-call summaries,
    # flattened input/output paths, custom metadata), run your enrichment
    # script here, then `edd score --since N` to trigger + poll.
    # See references/trace-inspection.md for the pattern and _local/ for examples.

    if not wait:
        log.info(
            "run complete — traces tagged. Run enrichment then `edd score --since N`."
        )
        return

    # 6 + 7. --wait: resolve target judges, trigger, poll, print.
    # Union CLI flag with per-scenario evaluators — keeps judge cost scoped to
    # the dimensions each intent actually exercises.
    scenario_targets: set[str] = set()
    for sc in scenarios:
        scenario_targets.update(sc.get("evaluators") or [])
    targets = (flag_targets | scenario_targets) or None

    evals = client.get_evaluators().get("content", [])
    project_evals = [ev for ev in evals if ev.get("project_name") == project]

    def _name(ev: dict) -> str:
        schema = ev.get("code", {}).get("schema") or [{}]
        return schema[0].get("name", ev.get("name", ""))

    if targets:
        project_evals = [ev for ev in project_evals if _name(ev) in targets]
    else:
        project_evals = [ev for ev in project_evals if ev.get("enabled")]

    if not project_evals:
        console.print("[yellow]no judges matched[/yellow]")
        return

    project_id = client.get_project_id(project)
    triggered_after = datetime.now(timezone.utc).isoformat()
    client.trigger_evaluation(project_id, trace_ids, [ev["id"] for ev in project_evals])
    log.info("triggered %d judges on %d traces", len(project_evals), len(trace_ids))

    expected_names = {_name(ev) for ev in project_evals}
    scored = poll_scores(client, trace_ids, timeout, expected_names, triggered_after)
    if not print_results(scored):
        raise typer.Exit(1)


@app.command()
def score(
    project: str = typer.Option(DEFAULT_PROJECT, "--project"),
    since: int = typer.Option(
        10,
        "--since",
        help="Trigger + poll judges on traces from the last N minutes.",
    ),
    timeout: int = typer.Option(120),
    evaluators: str = typer.Option(
        None,
        "--evaluators",
        "-e",
        help="Comma-separated judge names. Defaults to all project evaluators.",
    ),
):
    """Trigger judges on recent traces and print the score table.

    Run after `cli.py run` (and any custom enrichment) to score the traces
    that just landed without re-running the scenarios.
    """
    flag_targets = {n.strip() for n in evaluators.split(",")} if evaluators else set()
    client = OpikClient()
    from_str = (datetime.now(timezone.utc) - timedelta(minutes=since)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )

    traces = client.search_traces(project, from_time=from_str)
    trace_ids = [t["id"] for t in traces]
    if not trace_ids:
        console.print(f"[yellow]no traces found in the last {since}m[/yellow]")
        raise typer.Exit(1)
    log.info("found %d traces", len(trace_ids))

    evals = client.get_evaluators().get("content", [])
    project_evals = [ev for ev in evals if ev.get("project_name") == project]

    def _name(ev: dict) -> str:
        schema = ev.get("code", {}).get("schema") or [{}]
        return schema[0].get("name", ev.get("name", ""))

    if flag_targets:
        project_evals = [ev for ev in project_evals if _name(ev) in flag_targets]
    # No filter by enabled — score is an explicit manual trigger; disabled judges fire too.

    if not project_evals:
        console.print("[yellow]no judges found in project — create them first[/yellow]")
        raise typer.Exit(1)

    project_id = client.get_project_id(project)
    triggered_after = datetime.now(timezone.utc).isoformat()
    client.trigger_evaluation(project_id, trace_ids, [ev["id"] for ev in project_evals])
    log.info("triggered %d judges on %d traces", len(project_evals), len(trace_ids))

    expected = {_name(ev) for ev in project_evals}
    scored = poll_scores(client, trace_ids, timeout, expected, triggered_after)
    if not print_results(scored):
        raise typer.Exit(1)


@app.command()
def check():
    """Verify env vars + Opik reachable + agent reachable. Run before first invocation."""
    required = ["OPIK_URL", "OPIK_API_KEY", "OPIK_OTLP_ENDPOINT", "AGENT_ENDPOINT"]
    errors = []
    for v in required:
        ok = bool(os.environ.get(v))
        console.print(f"  [{'green' if ok else 'red'}]{'✓' if ok else '✗'}[/] {v}")
        if not ok:
            errors.append(v)

    if not errors:
        try:
            OpikClient()._request("GET", "/v1/private/projects", params={"size": 1})
            console.print("  [green]✓[/] Opik reachable")
        except Exception:
            log.exception("Opik connectivity check failed")
            console.print("  [red]✗[/] Opik unreachable — see log for details")
            errors.append("OPIK")

        try:
            import httpx as _httpx

            url = settings.agent_endpoint
            # Use the base host — HEAD on the run endpoint may not be supported.
            base = url.split("/agents/")[0] if "/agents/" in url else url
            _httpx.get(base, timeout=5.0)
            console.print("  [green]✓[/] Agent endpoint reachable")
        except Exception:
            log.exception("Agent endpoint check failed")
            console.print(
                "  [red]✗[/] AGENT_ENDPOINT unreachable — see log for details"
            )
            errors.append("AGENT_ENDPOINT")

    if errors:
        console.print(f"\n[red]failed: {', '.join(errors)}[/red]")
        raise typer.Exit(1)
    console.print("\n[green]ok[/green]")


if __name__ == "__main__":
    app()
