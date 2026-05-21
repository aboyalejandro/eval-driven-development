# DEVELOPMENT.md — local install

How to wire `edd` (this repo) into another project on your machine so the `/edd:*` slash commands work in Claude Code and the `edd*` CLIs run from that project's venv.

Two placeholders to substitute throughout:

- `<edd-repo>` — absolute path to **this** repo (the one you're reading now). From inside it: `pwd`. Example: `/Users/you/code/eval-driven-development`.
- `<your-project>` — absolute path to the project you want to evaluate (the agent's repo).

> Tip: paste the literal output of `pwd` — don't keep the angle brackets.

---

## 1. Register the plugin (one-time per machine)

Claude Code discovers plugins via a **marketplace** (a manifest listing one or more plugins). The repo ships `.claude-plugin/marketplace.json` for this.

Inside any Claude Code session (substitute `<edd-repo>` with the absolute path from `pwd` above):

```
/plugin marketplace add <edd-repo>
/plugin install edd@edd
```

Concrete example:

```
/plugin marketplace add /Users/you/code/eval-driven-development
/plugin install edd@edd
```

After install, every Claude Code session sees `/edd:edd`, `/edd:scope-agent`, `/edd:scope-evals`, `/edd:run`, `/edd:experiment`, `/edd:expand`.

**Note:** symlinking the repo into `~/.claude/plugins/` does **not** auto-enable — the marketplace + install flow is the supported path.

## 2. Install the Python CLI into the target project's venv

```bash
cd <your-project>
source .venv/bin/activate            # or create: python3 -m venv .venv && source .venv/bin/activate
pip install -e <edd-repo>/scripts
```

Verify:

```bash
which edd edd-build edd-run edd-inspect
edd --help
```

All four should resolve to the active venv.

## 3. Wire `.env` in the target project root

```bash
cd <your-project>
cp <edd-repo>/.env.example .env
```

Fill these keys (all required):

| Key | What |
|---|---|
| `OPIK_URL` | Opik base URL |
| `OPIK_API_KEY` | Opik auth header value |
| `OPIK_OTLP_ENDPOINT` | Where the agent ships traces (the agent reads this, not `edd`) |
| `AGENT_ENDPOINT` | HTTP URL of the agent under test |
| `OPIK_WORKSPACE` | Required for Comet-hosted Opik; ignored by self-hosted |
| `AGENT_ADAPTER` | Optional. `module:function` if your agent's HTTP contract differs from the default `{"message", "session_id"}` → `{"content"}` |

## 4. Sanity-check

```bash
edd check
```

Green = Opik reachable + agent reachable. Fix red rows before running anything else.

## 5. First invocation

The agent must be serving HTTP on `AGENT_ENDPOINT`. Boot it first (e.g., `docker compose up`).

In Claude Code, from the target project's dir:

```
/edd:edd
```

The router asks two questions:
- **Mode** — `1` quick trace analysis (optionally with `edd score`), `2` dataset + experiment in Opik UI
- **Aggression** — `1` happy path, `2` mixed, `3` adversarial

It writes `.edd/session.json` (gitignored) and dispatches. First time, it'll route through `/edd:scope-agent` to derive `regressions.txt` and `.edd/promises.md` from your agent source.

Or skip the router and call a phase directly:

```
/edd:scope-agent     # first time only — extract promise inventory
/edd:scope-evals     # create missing Opik judges
/edd:run             # inner loop (optional `edd score` for sim-only judge results)
/edd:experiment      # outer loop (Opik UI scorecard)
/edd:expand          # optional — grow the dataset with AI variants targeted at coverage gaps
```

See [`skills/CLAUDE.md`](skills/CLAUDE.md) for the full DAG and per-skill details.

## 6. Files that live in the target project (gitignored at framework level)

Commit these in **your** project repo — they encode your agent's specifics:

| File | Written by | Purpose |
|---|---|---|
| `regressions.txt` | `/edd:scope-agent` | 5–8 baseline scenarios — one per core promise |
| `scenarios.txt` | `/edd:run` | Diff-specific scenarios, regenerated per session |
| `_local/create_evaluators.py` | `/edd:scope-evals` | Idempotent script that creates judges in Opik |
| `_local/enrich_traces_<sdk>.py` | you (per SDK) | Normalize trace shape; pick `agno`, `claude`, or `openai` template |
| `_local/my_adapter.py` | you (optional) | Custom HTTP adapter when agent contract differs from default |
| `.edd/session.json` | router | Shared state across sub-skills (auto-managed) |

## 7. Updating

The plugin is installed as a reference to this repo, so:

- **Python CLI** (`scripts/`) — live thanks to `pip install -e`. Edit and re-run; no reinstall.
- **Skill bodies** — fresh-read each invocation.
- **Skill descriptions, `plugin.json`, new/removed skills** — restart Claude Code in the target project so the description-match index rebuilds.
- **`.env`** — re-run the command; loaded at process start.

To bump the plugin version after editing this repo: edit `version` in `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`, then in Claude Code:

```
/plugin marketplace update edd
```

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/edd:*` not in slash list | Plugin not installed in this session | Re-run `/plugin install edd@edd`; restart Claude Code |
| `/plugin marketplace add` errors "marketplace file not found" | `.claude-plugin/marketplace.json` missing or path wrong | Verify file exists at `<repo>/.claude-plugin/marketplace.json` |
| `edd: command not found` | venv not active or CLI not installed | `source .venv/bin/activate` + `pip install -e <repo>/scripts` |
| `edd check` fails on Opik | Bad `OPIK_URL` or `OPIK_API_KEY` | Verify in `.env`; for Comet-hosted, also set `OPIK_WORKSPACE` |
| `edd check` fails on agent | Agent not running on `AGENT_ENDPOINT` | `curl $AGENT_ENDPOINT` should return something |
| All judges score 0 | Enrichment skipped — `metadata.*` paths empty | Run `_local/enrich_traces_<sdk>.py --since-minutes 5` between `edd run` and `edd score` |
| Traces don't appear in Opik | Agent isn't shipping OTEL | Check `OPIK_OTLP_ENDPOINT` in the agent's own env, not `edd`'s |

---

For the conceptual model (modes, aggression levels, phase DAG) see [`README.md`](README.md). For module-level docs see [`CLAUDE.md`](CLAUDE.md) (sitemap).
