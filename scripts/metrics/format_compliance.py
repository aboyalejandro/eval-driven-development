"""Format compliance metric. Self-contained for Opik server execution."""

import json
import re
from typing import Any

from opik.evaluation.metrics import base_metric, score_result


def _final_content(output: str | dict | None) -> str:
    if output is None:
        return ""
    if isinstance(output, dict):
        content = output.get("content", "")
        return content if isinstance(content, str) else json.dumps(content)
    return str(output)


class FormatCompliance(base_metric.BaseMetric):
    """Fails when output does not match a required regex pattern or JSON shape."""

    def __init__(
        self,
        name: str = "format_compliance",
        pattern: str | None = None,
        require_json: bool = False,
    ):
        self.name = name
        self.pattern = pattern
        self.require_json = require_json

    def score(
        self,
        input: str,
        output: str | dict | None,
        metadata: dict | None = None,
        **ignored_kwargs: Any,
    ) -> score_result.ScoreResult:
        content = _final_content(output)
        if not content:
            return score_result.ScoreResult(
                name=self.name,
                value=0,
                reason="Empty output — format cannot be verified.",
            )
        if self.require_json:
            try:
                json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return score_result.ScoreResult(
                    name=self.name, value=0, reason="Output is not valid JSON."
                )
        if self.pattern and not re.search(self.pattern, content):
            return score_result.ScoreResult(
                name=self.name,
                value=0,
                reason=f"Output does not match required pattern: {self.pattern!r}.",
            )
        return score_result.ScoreResult(
            name=self.name, value=1, reason="Output matches expected format."
        )
