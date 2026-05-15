#!/usr/bin/env python3
"""Eval-Driven Development CLI.

python cli.py run "Hello agent" --wait
python cli.py run scenarios.txt --wait --evaluators "Faithfulness,Format Compliance"
python cli.py check
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))

from agent import run_scenario
from opik_client import OpikClient
from results import poll_scores, print_results

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

app = typer.Typer()
console = Console()
DEFAULT_PROJECT = os.environ.get("EVAL_PROJECT", "Testing")


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
    load_dotenv()
    scenarios = _load_scenarios(message_or_file)
    flag_targets = {n.strip() for n in evaluators.split(",")} if evaluators else set()
    asyncio.run(_run(scenarios, project, wait, timeout, flag_targets))


async def _run(
    scenarios: list[dict],
    project: str,
    wait: bool,
    timeout: int,
    flag_targets: set[str],
):
    # The agent under test owns its own OTEL → Opik tracing (see PREREQUISITES.md).
    # This process is just an HTTP client; we don't instrument it.

    run_id = uuid.uuid4().hex[:8]
    start = datetime.now(timezone.utc)

    # Union CLI flag with per-scenario evaluators. A scenario's `evaluators` field
    # declares which judges should fire on its trace — keeps judge cost scoped to
    # the dimension each intent actually exercises.
    scenario_targets: set[str] = set()
    for sc in scenarios:
        scenario_targets.update(sc.get("evaluators") or [])
    targets = (flag_targets | scenario_targets) or None

    # 2. Run scenarios. Agent name is prefixed `sim-<run_id>-` for filtering.
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

    # If your judges need trace-shape normalization (e.g. tool-call summaries
    # for OpenInference-instrumented agents, or flattening provider-specific
    # input/output shapes), run that enrichment between this tagging step and
    # the evaluator trigger below. The framework intentionally stays neutral —
    # see references/trace-inspection.md for the pattern.

    # 6. Pick judges, trigger evaluation.
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
    client.trigger_evaluation(project_id, trace_ids, [ev["id"] for ev in project_evals])
    log.info("triggered %d judges on %d traces", len(project_evals), len(trace_ids))

    # 7. Optionally wait for scores and print the table.
    if wait:
        expected = {_name(ev) for ev in project_evals}
        scored = poll_scores(client, trace_ids, timeout, expected)
        if not print_results(scored):
            raise typer.Exit(1)


@app.command()
def check():
    """Verify env vars + Opik reachable + agent reachable. Run before first invocation."""
    load_dotenv()
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
        except Exception as e:
            console.print(f"  [red]✗[/] Opik: {e}")
            errors.append("OPIK")

        try:
            import httpx as _httpx
            url = os.environ["AGENT_ENDPOINT"]
            # Use the base host — HEAD on the run endpoint may not be supported.
            base = url.split("/agents/")[0] if "/agents/" in url else url
            _httpx.get(base, timeout=5.0)
            console.print("  [green]✓[/] Agent endpoint reachable")
        except Exception as e:
            console.print(f"  [red]✗[/] AGENT_ENDPOINT unreachable: {e}")
            errors.append("AGENT_ENDPOINT")

    if errors:
        console.print(f"\n[red]failed: {', '.join(errors)}[/red]")
        raise typer.Exit(1)
    console.print("\n[green]ok[/green]")


if __name__ == "__main__":
    app()
