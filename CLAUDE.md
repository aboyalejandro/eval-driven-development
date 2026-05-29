# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Conceptual foundation

This framework operationalizes Anthropic's **["Demystifying evals for AI agents"](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)**. Base eval-design judgment calls (grader choice, scoring convention, what to test) on its fundamentals — they are agent-agnostic and constant. Concept → artifact mapping:

- **Regression evals** (≈100% pass, catch backsliding) → `regressions.txt`. **Capability evals** (low pass, a hill to climb) → session `scenarios.txt`.
- **Model-based graders** (LLM-as-judge) → Opik evaluators (`scope-evals`). **Code-based graders** (deterministic, free, fast) → code metrics (`scripts/metrics/`).
- **Grade outcomes, not paths**; combine grader types; read the transcripts; a green run isn't proof (non-determinism).

Load [`references/eval-fundamentals.md`](references/eval-fundamentals.md) for the distilled *why* before making an eval-design call you can't already ground in a per-step reference.

## Sitemap

Distributed CLAUDE.md docs — load the one closest to where you're working:

| Area | Doc | What lives there |
|---|---|---|
| Skills (workflow entry) | [`skills/CLAUDE.md`](skills/CLAUDE.md) | Sub-skill index, pipeline DAG, shared session state, cross-cutting anti-patterns / stopping rules / naming conventions |
| Framework engine | [`scripts/CLAUDE.md`](scripts/CLAUDE.md) | Package layout, console scripts → modules, install |
| Inner loop (CLI) | [`scripts/setup/CLAUDE.md`](scripts/setup/CLAUDE.md) | `edd run` / `edd score` / `edd check`, trace tagging, custom adapters |
| Outer loop (CLI) | [`scripts/simulation/CLAUDE.md`](scripts/simulation/CLAUDE.md) | `edd-build` / `edd-run` / `edd-inspect`, dataset naming |
| Opik REST + settings | [`scripts/shared/CLAUDE.md`](scripts/shared/CLAUDE.md) | `OpikClient` surface, env vars (canonical list), REST coupling caveat |
| Decision guides | [`references/CLAUDE.md`](references/CLAUDE.md) | Index of `references/*.md` and when to load each |

For first-time setup steps see [`DEVELOPMENT.md`](DEVELOPMENT.md). For the integration contract see [`PREREQUISITES.md`](PREREQUISITES.md). For required env vars see [`scripts/shared/CLAUDE.md`](scripts/shared/CLAUDE.md).

## Key constraints (gotchas not documented elsewhere)

- `create_agent` must name the agent starting with `{run_id}-` (which equals the branch tag) so traces are filterable by branch tag.
- Don't inject context by concatenating into the user message — mirror how production traffic arrives.
- `--dry-run` before every `edd-build` to verify the extractor shape.
- Supply `--extractor module:function` when trace shape differs from defaults (`trace.input.user_message` / `trace.output.assistant_response`).
- Dataset naming convention: `<project>-<topic>-v<N>`. Bump `<N>` whenever the item shape changes — cross-version score comparisons are noise.

## Per-agent artifacts (gitignored at framework level)

`scenarios.txt` and `regressions.txt` (root) are gitignored — they're per-agent, not framework files. The framework ships `*.example.txt` templates only.

Fresh-agent workflow:
1. Run [`references/agent-analysis.md`](references/agent-analysis.md) extraction → produce a promise inventory.
2. Copy `regressions.example.txt` → `regressions.txt`. Populate with 5–8 baseline scenarios (one per core promise). **Commit this in your fork / working branch** — it persists across sessions.
3. Copy `scenarios.example.txt` → `scenarios.txt`. Regenerate diff-specific scenarios per session.

**Always check for an existing `regressions.txt` before re-deriving baselines.** Re-running agent-analysis every session wastes tokens and drifts the baseline.

## Caveat — Opik REST coupling

The framework is tightly coupled to Opik's REST API. Endpoints used by `scripts/shared/opik_client.py` are catalogued in [`references/opik-endpoints.md`](references/opik-endpoints.md). If a previously-working setup starts erroring after time has passed, suspect API drift first — check Opik release notes before debugging the framework.
