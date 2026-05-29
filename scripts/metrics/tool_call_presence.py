"""Tool-call presence metric. Self-contained for Opik server execution."""

import json
import re
from typing import Any

from opik.evaluation.metrics import base_metric, score_result


def _extract_tool_names(output: str | dict | None) -> list[str]:
    """Return tool names called, from JSON output messages or plain-text heuristic."""
    if output is None:
        return []
    if isinstance(output, dict):
        names = []
        for msg in output.get("messages", []):
            for tc in msg.get("tool_calls") or []:
                fn = (tc.get("function") or {}).get("name") or tc.get("name")
                if fn:
                    names.append(fn)
        if names:
            return names
        content = output.get("content", "")
        output = content if isinstance(content, str) else json.dumps(content)
    return re.findall(r'"name"\s*:\s*"([^"]+)"', str(output))


class ToolCallPresence(base_metric.BaseMetric):
    """Fails when no tool call is present in the trace output."""

    def __init__(
        self, name: str = "tool_call_presence", required_tool: str | None = None
    ):
        self.name = name
        self.required_tool = required_tool

    def score(
        self,
        input: str,
        output: str | dict | None,
        metadata: dict | None = None,
        **ignored_kwargs: Any,
    ) -> score_result.ScoreResult:
        # Enriched traces populate metadata.tools_called — prefer that over output parsing.
        if metadata and metadata.get("tools_called"):
            raw = metadata["tools_called"]
            tools = raw if isinstance(raw, list) else [raw]
        else:
            tools = _extract_tool_names(output)
        if not tools:
            return score_result.ScoreResult(
                name=self.name, value=0, reason="No tool calls found in output."
            )
        if self.required_tool and self.required_tool not in tools:
            return score_result.ScoreResult(
                name=self.name,
                value=0,
                reason=f"Required tool '{self.required_tool}' not called. Found: {tools}.",
            )
        return score_result.ScoreResult(
            name=self.name, value=1, reason=f"Tool calls present: {tools}."
        )
