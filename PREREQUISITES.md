# Prerequisites

What needs to be in place before this framework produces useful scores. Read this before `agent-analysis.md` — if any of the items below are missing, the rest of the loop has nothing to consume.

## Integration contract

The framework makes three assumptions about the agent under test:

### 1. Agent reachable over HTTP

- Exposed at a URL set via `AGENT_ENDPOINT`
- Accepts a message payload and returns a text response
- Can be invoked headlessly (no UI dependency)

The shipped `scripts/agent.py` adapter sends a JSON POST with `{"message": "...", "session_id": "..."}` and expects a JSON response with a `content` field. It is **synchronous by default** — one request per scenario turn, no streaming. Session ID is sent on every turn (multi-turn continuity is opt-in at the agent side). If your agent uses a different field name (e.g. `thread_id`), a different body shape, or streaming, edit `arun()` — it's a starting template, not a contract you have to satisfy verbatim.

Default HTTP timeout is **300 seconds**. Agents that call multiple MCP tools sequentially (OpenAI Agents SDK, multi-step Agno flows) can take 2–4 minutes per scenario. If you see `ReadTimeout` errors, the agent is still processing — the timeout is sufficient for most cases; increase it in `arun()` if your agent is slower.

Any runtime that can be exposed as an HTTP endpoint works: Agno, LangGraph, Pydantic AI, FastAPI wrappers around an SDK call, raw Anthropic/OpenAI SDK calls behind a thin server, custom orchestrators. The framework doesn't care which.

#### Customising the HTTP adapter

If your agent's contract differs from the default, set `AGENT_ADAPTER` in `.env`:

```
AGENT_ADAPTER=_local.my_adapter:create_agent
```

The adapter module must live in `_local/` (gitignored) and expose a `create_agent` function with this signature:

```python
# _local/my_adapter.py
import httpx, os
from types import SimpleNamespace

AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT")

async def create_agent(session_id: str, run_id: str, context: dict | None = None):
    class AgentProxy:
        def __init__(self):
            self.name = f"sim-{run_id}"
            self._session_id = session_id

        async def arun(self, message: str):
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    AGENT_ENDPOINT,
                    headers={"Authorization": f"Bearer {os.getenv('AGENT_TOKEN')}"},
                    json={"input": message, "thread_id": self._session_id},
                )
                resp.raise_for_status()
                return SimpleNamespace(content=resp.json()["text"])

    return AgentProxy()
```

Only override what differs — body shape, field names, auth, timeout, response parsing. Leave `AGENT_ADAPTER` unset when the generic default matches your agent (most REST agents do).

The substack-author-agent (Agno, Anthropic SDK, OpenAI Agents SDK) all work with the generic default — verified with one trace each, no adapter needed.

### 2. Agent emits traces to Opik directly

- Agent owns its tracing setup (OTEL exporter pointed at the Opik OTLP endpoint, or the Opik SDK)
- This framework does *not* instrument the agent runtime — it consumes traces via Opik's REST API
- Trace names are set by the agent runtime, not by this framework — the adapter's name never propagates to external agent traces. Sim runs are isolated by time window + dedicated project, not by trace name prefix.

If the agent doesn't already trace to Opik, wire it up before running this loop. The eval loop is built on the premise that the same trace pipeline runs in sim and in production — that's what gives the scores production-parity.

### 3. Opik instance + dedicated testing project

- Hosted (`comet.com/opik`) or self-hosted instance
- A separate project for sim traffic — never mix with production
- Evaluator rules ("judges") defined in that project. For the inner loop, create them with `enabled=False, sampling_rate=0` (manual-trigger mode) — the framework fires them on exactly the traces it just ran. See `references/evaluator-selection.md` Step 4 for when to switch to auto-sample.
- API key with read access to traces and write access to datasets, experiments, automations

## Caveat: REST API coupling

This framework is tightly coupled to Opik's REST API surface. The endpoints in use are documented in `references/opik-endpoints.md` and the wrapper lives at `scripts/opik_client.py`.

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

## Judge model dependency

LLM-as-judge evaluators run against the model you configure in the rule (e.g. `claude-haiku-4-5-20251001`, `gpt-4o`). The model must have a valid API key configured in your Opik workspace — the framework doesn't supply credentials. If scores never land after a trigger, check the evaluator logs at `GET /v1/private/automations/evaluators/{id}/logs`: a "no API key configured" error means the workspace has no credential for that provider. Switch to a model your workspace already has access to.
