# Trace enrichment — normalizing the shape your judges read

Once you know your trace shape ([`trace-inspection.md`](trace-inspection.md)), decide whether judges read from native SDK paths or from a normalized `metadata.*` namespace. This doc covers the second path — the recommended one — and ships skeleton enrichment scripts per SDK.

## Two patterns

### Pattern A — Judge variables point at the native shape

Works only when all traces in the project come from the same SDK. Breaks the moment you run a second SDK against the same Opik project.

```python
variables = {
    "input": "input.input.value",     # OpenInference only
    "output": "output.output.value",  # OpenInference only
}
```

**Do not use if you mix SDKs in one Opik project.** Use Pattern B instead.

### Pattern B — Normalize into metadata, point variables there (recommended)

An enrichment script extracts SDK-native paths and writes normalized fields to `trace.metadata`. Evaluators always read `metadata.*` — they never see raw SDK trace shapes.

This is mandatory when:
- You run multiple SDKs against one Opik project
- Judges need tool call data (tool outputs aren't on the trace directly)
- You want evaluators to survive a future runtime swap

## Skeleton (adapt per SDK)

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

    # --- Tool span extraction ---
    # Walk by both signals — `span.type == "tool"` (native instrumentors) AND
    # `openinference.span.kind == "TOOL"` in input attributes (Agno, LangChain,
    # OpenAI Agents SDK and other OpenInference-based instrumentors that leave
    # `span.type = "general"`). Using only one filter loses tool data — see the
    # `trace.has_tool_spans` anti-pattern below.
    spans = client.get_spans(project, trace_id, size=200).get("content", [])

    def _is_tool_span(s: dict) -> bool:
        if s.get("type") == "tool":
            return True
        attrs = s.get("input") or {}
        if isinstance(attrs, dict) and attrs.get("openinference.span.kind") == "TOOL":
            return True
        return False

    tool_spans = [s for s in spans if _is_tool_span(s)]

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

## SDK discrimination — required when projects mix SDKs

In a shared project, each enrichment script must skip traces that belong to other SDKs. Check the trace input shape before processing:

```python
# Skip if not your SDK's trace
if "input.value" not in trace.get("input", {}):   # Agno check
    continue
if "message" not in trace.get("input", {}):        # Claude SDK check
    continue
if (trace.get("metadata") or {}).get("created_from") != "openai-agents":  # OpenAI check
    continue
```

## Truncation

If a trace has more tool calls than `MAX_TOOLS`, some outputs won't be visible. Your grounding rubric should give benefit of the doubt when `len(tools_called) > len(tool_outputs)`.

## When to run enrichment

Between `edd run` (emits traces) and `edd score` (fires judges). The standard flow:

```bash
edd run scenarios.txt                                  # emit + tag, exit
python _local/enrich_traces_<sdk>.py --since-minutes 5  # normalize metadata.*
edd score --since 10                                    # judges read normalized fields
```

## Judges read from `metadata.*`

```python
variables = {
    "input": "metadata.user_message",
    "output": "metadata.assistant_response",
    "tools_called": "metadata.tools_called",
    "tool_outputs": "metadata.tool_outputs",
}
```

## Anti-patterns

- **Baking instrumentor assumptions into the framework core.** Enrichment lives in your fork's `_local/`. The setup CLI must not assume any SDK.
- **Using `trace.has_tool_spans` for trajectory judges.** Opik computes this from `span.type`, not span attributes. Many instrumentors set `span.type = "general"` while emitting `kind=TOOL` in attributes. Walk spans yourself.
- **Putting the user message in a single hardcoded variable across all agents.** OpenInference uses `input.value`, LangChain uses `messages[-1].content`, Anthropic raw uses `messages` array. Normalize to `metadata.user_message` once; let judges depend on the normalized shape only.

## See also

- [`trace-inspection.md`](trace-inspection.md) — fetch a trace and identify its native shape first
- [`evaluator-selection.md`](evaluator-selection.md) — judges read from `metadata.*` paths this script populates
- [`../skills/run/SKILL.md`](../skills/run/SKILL.md) — run enrichment between `edd run` and `edd score`
- [`../scripts/shared/CLAUDE.md`](../scripts/shared/CLAUDE.md) — `update_trace_metadata` on `OpikClient`
