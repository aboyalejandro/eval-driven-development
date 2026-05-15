# Prerequisites

What needs to be in place before this framework produces useful scores. Read this before `agent-analysis.md` — if any of the items below are missing, the rest of the loop has nothing to consume.

## Integration contract

The framework makes three assumptions about the agent under test:

### 1. Agent reachable over HTTP

- Exposed at a URL set via `AGENT_ENDPOINT`
- Accepts a message payload and returns a text response
- Can be invoked headlessly (no UI dependency)

The shipped `scripts/agent.py` adapter assumes form-encoded POST with `message` + `session_id` and a JSON response with a `content` field. If your agent's request/response shape differs, edit `arun()` — it's a starting template, not a contract you have to satisfy verbatim.

Any runtime that can be exposed as an HTTP endpoint works: Agno, LangGraph, Pydantic AI, FastAPI wrappers around an SDK call, raw Anthropic/OpenAI SDK calls behind a thin server, custom orchestrators. The framework doesn't care which.

### 2. Agent emits traces to Opik directly

- Agent owns its tracing setup (OTEL exporter pointed at the Opik OTLP endpoint, or the Opik SDK)
- This framework does *not* instrument the agent runtime — it consumes traces via Opik's REST API
- Traces must include the agent name (`sim-{run_id}-{AGENT_NAME}` set by the adapter) so sim runs are filterable

If the agent doesn't already trace to Opik, wire it up before running this loop. The eval loop is built on the premise that the same trace pipeline runs in sim and in production — that's what gives the scores production-parity.

### 3. Opik instance + dedicated testing project

- Hosted (`comet.com/opik`) or self-hosted instance
- A separate project for sim traffic — never mix with production
- Evaluator rules ("judges") defined in that project, enabled, and sampled
- API key with read access to traces and write access to datasets, experiments, automations

## Caveat: REST API coupling

This framework is tightly coupled to Opik's REST API surface. The endpoints in use are documented in `references/opik-endpoint-cheatsheet.md` and the wrapper lives at `scripts/opik_client.py`.

If you hit unexpected errors on what was previously a working setup:

1. Check the Opik release notes for endpoint changes since you last updated.
2. Diff `scripts/opik_client.py` against the endpoints in your Opik version's docs.
3. Pin a known-working Opik version when stability matters more than features.

Endpoint drift is the most common failure mode after a long pause between runs. The framework treats Opik's REST surface as a stable contract, but in practice it moves.

## Quick sanity check

Before the first sim run:

```bash
python scripts/cli.py check
```

This hits the Opik project endpoint and the evaluators endpoint. If it errors:

- 401 → `OPIK_API_KEY` is wrong or expired
- 404 on project → `EVAL_PROJECT` doesn't exist; create it in the Opik UI
- Connection error → `OPIK_URL` is wrong or the instance is unreachable
- No evaluators returned → judges haven't been defined yet; create them in the project
