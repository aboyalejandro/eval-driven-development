#!/usr/bin/env python3
"""edd-expand — AI-driven dataset expansion via Opik /datasets/expand. See scripts/simulation/CLAUDE.md."""

import json

import typer
from rich.console import Console

from shared.opik_client import OpikClient
from shared.session import branch_tag_warning, session_tags
from shared.settings import settings

console = Console()
app = typer.Typer(add_completion=False)


@app.command()
def main(
    dataset_name: str = typer.Option(
        ..., "--dataset-name", help="Existing Opik dataset to expand."
    ),
    model: str = typer.Option(
        ...,
        "--model",
        help="LLM for synthetic generation (e.g. anthropic/claude-sonnet-4-6, openai/gpt-4o).",
    ),
    count: int = typer.Option(
        10, "--count", help="Number of synthetic samples to generate."
    ),
    variation_instructions: str | None = typer.Option(
        None,
        "--variation-instructions",
        help="Free-form steering — the agent-specific gap or behaviour the expansion should target.",
    ),
    custom_prompt: str | None = typer.Option(
        None,
        "--custom-prompt",
        help="Override the auto-generated prompt entirely. Mutually exclusive with --variation-instructions in practice.",
    ),
    preserve_field: list[str] = typer.Option(
        [],
        "--preserve-field",
        help="Field name(s) whose pattern the expansion must preserve. Repeatable. Pass the fields that define your item shape contract (e.g. user_message, assistant_response).",
    ),
    max_tokens: int | None = typer.Option(
        None,
        "--max-tokens",
        help="Max completion tokens. Required for Anthropic models (defaults to 4000 server-side).",
    ),
    extra_tag: list[str] = typer.Option(
        [],
        "--tag",
        help="Extra tag stamped on synthetic items via dataset metadata. Stacks on session tags.",
    ),
    branch_tag: str | None = typer.Option(
        None,
        "--branch-tag",
        help="Optional branch tag — used only for the main/master warning, not the expansion call.",
    ),
    allow_main: bool = typer.Option(
        False,
        "--allow-main",
        help="Silence the warning when --branch-tag references main/master.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print generated samples to stdout without persisting. Always run this first.",
    ),
):
    """Generate synthetic dataset items, optionally persist them."""
    if branch_tag and not allow_main and (w := branch_tag_warning(branch_tag)):
        console.print(f"[yellow]{w}[/yellow]")

    client = OpikClient()
    dataset_id = client.get_dataset_id(dataset_name)
    if not dataset_id:
        console.print(f"[red]dataset not found: {dataset_name}[/red]")
        raise typer.Exit(code=1)

    plan = {
        "dataset": dataset_name,
        "dataset_id": dataset_id,
        "model": model,
        "count": count,
        "preserve_fields": preserve_field or None,
        "variation_instructions": variation_instructions,
        "custom_prompt": custom_prompt,
    }
    console.print(json.dumps(plan, indent=2))

    samples = client.expand_dataset(
        dataset_id=dataset_id,
        model=model,
        sample_count=count,
        preserve_fields=preserve_field or None,
        variation_instructions=variation_instructions,
        custom_prompt=custom_prompt,
        max_completion_tokens=max_tokens,
    )
    console.print(f"[bold]generated {len(samples)} sample(s)[/bold]")

    # Opik returns full DatasetItem objects ({id, source, data, ...}). Unwrap
    # to flat item dicts before insert_dataset_items re-wraps, otherwise the
    # real fields end up nested at data.data.<field>.
    flat = [{"id": s.get("id"), **(s.get("data") or {})} for s in samples]

    if dry_run:
        preview = flat[: min(3, len(flat))]
        console.print(json.dumps(preview, indent=2, default=str))
        console.print(
            "[yellow]dry-run — nothing persisted. Re-run without --dry-run to insert.[/yellow]"
        )
        return

    if not flat:
        console.print("[yellow]no samples generated — nothing to persist.[/yellow]")
        raise typer.Exit(code=1)

    client.insert_dataset_items(dataset_name, flat)
    base = settings.opik_url.rstrip("/")
    console.print(f"[green]inserted {len(flat)} item(s) into {dataset_name}[/green]")
    if base:
        console.print(f"  {base}/datasets/{dataset_id}")

    # Tags applied via session for traceability — not propagated to individual items
    # because Opik dataset items don't carry tags; the dataset itself does.
    tags = [*session_tags(), *extra_tag]
    if tags:
        console.print(f"[dim]session tags (informational): {tags}[/dim]")


if __name__ == "__main__":
    app()
