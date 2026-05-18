# Trace inspection — knowing where your judges look

LLM judges score traces by reading fields off the trace JSON via variable paths. The framework doesn't know what your traces look like — every instrumentation library emits them differently. Before you can write judges, you need to know your trace shape.

This doc covers (1) how to fetch a single trace via the Opik REST API and (2) the conventions you'll typically see. Once you know the shape, choose Pattern A or Pattern B in [`trace-enrichment.md`](trace-enrichment.md) to wire judges against it.

## Step 1 — Fetch a real trace

Run one scenario against your agent (any user message). Confirm a trace lands in Opik, then pull it:

```python
from shared.opik_client import OpikClient
c = OpikClient()
trace = c._request("GET", f"/v1/private/traces/{TRACE_ID}")
print("top-level keys:", list(trace.keys()))
print("input:", trace["input"])
print("output:", trace["output"])
print("span_count:", trace["span_count"])
```

Three things to write down for each agent:

- **Top-level fields** — what's at `trace.*`? (`input`, `output`, `metadata`, `has_tool_spans`, `usage`, ...)
- **Input shape** — is `trace.input` a string, dict, or list? Where exactly is the user message?
- **Output shape** — same question for the assistant response.

## Step 2 — Recognise your tracing convention

What you'll typically see:

### OpenInference (Agno via `openinference-instrumentation-agno`)

```python
trace.input  = {
    "input.value": "<user message>",     # literal-dot key
    "agent.name": "...",
    "session.id": "...",
    "openinference.span.kind": "AGENT",
}
trace.output = {
    "output.value": "<assistant response>",
}
# Tool spans: span.input["openinference.span.kind"] == "TOOL" (not span.type!)
# Tool output: span.output["output.value"]
# Discriminator: "input.value" in trace.input
```

Note: Opik's top-level `trace.has_tool_spans` checks `span.type == "tool"` and **may report False** even when tool spans exist with `kind=TOOL` — because Agno sets `span.type = "general"`. Walk spans yourself.

### Anthropic SDK (`opik.integrations.anthropic.track_anthropic`)

```python
trace.input    = {"message": "<user message>", "session_id": "..."}
trace.output   = {"output": "<assistant response>"}
trace.metadata = {"providers": ["anthropic"]}
# Tool spans: span.type == "tool"  ← reliable here
# Tool name: span.name
# Tool input: span.input["tool_input"] (subkey — span.input also has mcp_session)
# Tool output: span.output["output"] (JSON string)
# Discriminator: "message" in trace.input
```

### OpenAI Agents SDK (`opik.integrations.openai.agents.OpikTracingProcessor`)

```python
trace.input    = {"input": [{"role": "user", "content": "<user message>"}, ...]}
trace.output   = {"output": [{"type": "reasoning", ...}, {"type": "message", "content": [{"type": "output_text", "text": "..."}], ...}]}
trace.metadata = {"providers": ["openai"], "created_from": "openai-agents", "agents-trace-id": "..."}
# Tool spans: span.type == "tool"  ← reliable
# Tool name: span.name
# Tool input: json.loads(span.input["input"])  ← JSON string, not a dict
# Tool output: span.output.get("text") or span.output.get("output", "")
# Discriminator: trace.metadata.get("created_from") == "openai-agents"
```

### LangChain / LangGraph native

```python
trace.input  = {"messages": [{"role": "user", "content": "..."}], ...}
trace.output = {"messages": [...], "content": "..."}
```

### Raw OTEL or vendor-specific

Whatever the instrumentor decides. Read it once, write it down, design judge variables against it.

## Quick start — reverse-engineering an unfamiliar agent

1. Fire one scenario, find the trace ID (`search_traces` with a 5-min window).
2. `GET /v1/private/traces/{id}` and print every top-level key.
3. Drill into `input` and `output`: are they dicts? strings? lists? where's the user text? the assistant text?
4. `GET /v1/private/spans?project_name=X&trace_id=Y&size=200`. Filter spans where `(s["input"] or {}).get("openinference.span.kind")` exists. Print the distinct kinds.
5. Write the paths down.

15 minutes of inspection saves hours of guessing-then-debugging judge prompts.

## Next

→ [`trace-enrichment.md`](trace-enrichment.md) — Pattern A vs Pattern B, skeleton enrichment script, SDK discrimination.
→ [`evaluator-selection.md`](evaluator-selection.md) — wire those paths into judge definitions.
