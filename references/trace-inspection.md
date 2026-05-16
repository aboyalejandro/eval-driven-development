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

## Step 3 — Write enrichment if your judges need normalization

The Opik judge prompt's `variables` map points at trace JSON paths. Two patterns:

### Pattern A — Judge variables point at the native shape

Works only when all traces in the project come from the same SDK. Breaks the moment you run a second SDK against the same project.

```python
variables = {
    "input": "input.input.value",     # OpenInference only
    "output": "output.output.value",  # OpenInference only
}
```

**Do not use if you mix SDKs in one Opik project.** Use Pattern B instead.

### Pattern B — Normalize into metadata, point variables there (recommended)

The enrichment script extracts SDK-native paths and writes normalized fields to `trace.metadata`. Evaluators always read `metadata.*` — they never see raw SDK trace shapes.

This is mandatory when:
- You run multiple SDKs against one Opik project
- Judges need tool call data (tool outputs aren't on the trace directly)
- You want evaluators to survive a future runtime swap

**Skeleton (adapt per SDK):**

```python
import json

MAX_TOOLS = 10
MAX_CHARS = 800

def enrich_one(client, project, trace):
    trace_id = trace["id"]
    trace_input = trace.get("input") or {}

    # --- SDK-specific extraction (examples) ---
    # Agno/OpenInference:
    user_message = trace_input.get("input.value", "")
    assistant_response = (trace.get("output") or {}).get("output.value", "")

    # Anthropic SDK (track_anthropic):
    # user_message = trace_input.get("message", "")
    # assistant_response = (trace.get("output") or {}).get("output", "")

    # OpenAI Agents SDK:
    # user_message = (trace_input.get("input") or [{}])[0].get("content", "")
    # assistant_response = extract_openai_response(trace.get("output") or {})

    # --- Tool span extraction (varies by SDK) ---
    spans = client.get_spans(project, trace_id, size=200).get("content", [])
    tool_spans = [s for s in spans if s.get("type") == "tool"]
    # For Agno: filter by s["input"].get("openinference.span.kind") == "TOOL"

    tool_names = [s.get("name", "?") for s in tool_spans]
    tool_outputs = []
    for s in tool_spans[:MAX_TOOLS]:
        raw = (s.get("output") or {}).get("output", "")  # adjust key per SDK
        output_str = json.dumps(raw, default=str) if not isinstance(raw, str) else raw
        tool_outputs.append({"name": s.get("name", "?"), "output": output_str[:MAX_CHARS]})

    # --- Write normalized fields ---
    client.update_trace_metadata(trace_id, project, {
        "user_message": user_message,
        "assistant_response": assistant_response,
        "tools_called": tool_names,
        "tool_count": len(tool_names),
        "tool_outputs": tool_outputs,
    })
```

**SDK discrimination:** In a shared project, each enrichment script must skip traces that belong to other SDKs. Check the trace input shape before processing:

```python
# Skip if not your SDK's trace
if "input.value" not in trace.get("input", {}):   # Agno check
    continue
if "message" not in trace.get("input", {}):        # Claude SDK check
    continue
if (trace.get("metadata") or {}).get("created_from") != "openai-agents":  # OpenAI check
    continue
```

**Truncation:** if a trace has more tool calls than `MAX_TOOLS`, some outputs won't be visible. Grounding rubric should give benefit of the doubt when `len(tools_called) > len(tool_outputs)`.

Run enrichment between `edd run` and `edd score`.

Then judges read normalized metadata:

```python
variables = {
    "input": "metadata.user_message",
    "output": "metadata.assistant_response",
    "tools_called": "metadata.tools_called",
    "tool_outputs": "metadata.tool_outputs",
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
