# Trace inspection — knowing where your judges look

LLM judges score traces by reading fields off the trace JSON via variable paths. The framework doesn't know what your traces look like — every instrumentation library emits them differently. Before you can write judges, you need to know your trace shape.

This doc teaches:

1. How to fetch a single trace via the Opik REST API and inspect it.
2. How to identify your tracing convention (OpenInference, LangChain, raw OTEL, vendor-specific).
3. How to write a trace-enrichment step that normalizes the shape so generic judges work.

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

### OpenInference (Agno, LangChain via openinference-instrumentation-*, OpenAI Assistants via OpenInference SDK)

```python
trace.input  = {
    "input.value": "<user message>",     # literal-dot key
    "agent.name": "...",
    "session.id": "...",
    "openinference.span.kind": "AGENT",
    ...
}
trace.output = {
    "output.value": "<assistant response>",
    "output.mime_type": "application/json",
}
```

Tool spans (when present) have `openinference.span.kind = "TOOL"` in their input attributes. Note that Opik's top-level `trace.has_tool_spans` checks `span.type == "tool"` and **may report False** even when tool spans exist with `kind=TOOL` — because some instrumentors set `span.type = "general"`. Don't rely on the flag; walk spans yourself.

### LangChain / LangGraph native

```python
trace.input  = {"messages": [{"role": "user", "content": "..."}], ...}
trace.output = {"messages": [...], "content": "..."}
```

### Raw OTEL or vendor-specific

Whatever the instrumentor decides. Read it once, write it down, design judge variables against it.

## Step 3 — Write enrichment if your judges need normalization

The Opik judge prompt's `variables` map points at trace JSON paths. Two patterns:

### Pattern A — Judge variables point at the native shape

Cheapest. No enrichment needed.

```python
variables = {
    "input": "input.input.value",     # OpenInference
    "output": "output.output.value",
}
```

Use when your trace shape is stable and you don't need anything that isn't directly on the trace.

### Pattern B — Enrich the trace metadata, point variables there

Use when judges need derived fields (tool-call summaries, intent labels, span counts, latency buckets, anything you compute from the trace+spans).

```python
def enrich(client, project, trace_id):
    spans = client.get_spans(project, trace_id, size=200).get("content", [])
    tool_names = [
        s.get("name", "?")
        for s in spans
        if (s.get("input") or {}).get("openinference.span.kind") == "TOOL"
    ]
    client.update_trace_metadata(
        trace_id,
        project,
        {"tools_called": tool_names, "tool_count": len(tool_names)},
    )
```

Run this between `batch_update_traces` (tag step) and `trigger_evaluation` (judge step) — i.e. between `edd run` and `edd score`. The framework leaves this hook empty on purpose — see the comment block in `setup/cli.py` after the tagging step.

Then judges read it:

```python
variables = {
    "input": "input.input.value",
    "output": "output.output.value",
    "tools_called": "metadata.tools_called",
}
```

## Anti-patterns

- **Baking instrumentor assumptions into the framework core.** If the setup CLI called "extract tool calls from spans" by default, it would break for agents not using OpenInference. Keep enrichment in your fork's `_local/` script.
- **Using `trace.has_tool_spans` for trajectory judges.** Opik computes this from `span.type`, not span attributes. Many instrumentors set `span.type = "general"` while still emitting `kind=TOOL` in attributes. Walk spans yourself.
- **Putting the user message in a single variable across all agents.** OpenInference uses `input.value`, LangChain uses `messages[-1].content`, Anthropic raw uses `messages` array. The path is agent-specific; the judge prompt should be agnostic.

## Quick start — reverse-engineering an unfamiliar agent

1. Fire one scenario, find the trace ID (`search_traces` with a 5-min window).
2. `GET /v1/private/traces/{id}` and print every top-level key.
3. Drill into `input` and `output`: are they dicts? strings? lists? where's the user text? the assistant text?
4. `GET /v1/private/spans?project_name=X&trace_id=Y&size=200`. Filter spans where `(s["input"] or {}).get("openinference.span.kind")` exists. Print the distinct kinds.
5. Write down the paths your judges will need. Pick Pattern A or B accordingly.

15 minutes of inspection saves hours of guessing-then-debugging judge prompts.

Once you know your trace shape and have the variable paths written down, move to `evaluator-selection.md` to wire those paths into your judge definitions.
