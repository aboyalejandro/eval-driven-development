"""Registry of code-based metrics + Opik automation-rule payload builder."""

import inspect

from opik.evaluation.metrics import base_metric

from metrics.format_compliance import FormatCompliance
from metrics.system_prompt_leakage import SystemPromptLeakage
from metrics.tool_call_presence import ToolCallPresence

ALL_METRICS: list[type[base_metric.BaseMetric]] = [
    ToolCallPresence,
    FormatCompliance,
    SystemPromptLeakage,
]

# Default JSONPath argument mapping for score(input, output, metadata).
# Opik resolves dotted paths against the trace dict.
# Override per metric class via a class-level OPIK_ARGUMENTS dict.
DEFAULT_ARGUMENTS: dict[str, str] = {
    "input": "input.input.value",
    "output": "output.output.value",
    "metadata": "metadata",
}


def metric_arguments(metric_cls: type[base_metric.BaseMetric]) -> dict[str, str]:
    return getattr(metric_cls, "OPIK_ARGUMENTS", DEFAULT_ARGUMENTS)


def build_payload(
    metric_cls: type[base_metric.BaseMetric],
    project_id: str,
    enabled: bool = False,
    sampling_rate: float = 1.0,
) -> dict:
    """Build the POST body for /v1/private/automations/evaluators."""
    instance = metric_cls()
    return {
        "name": instance.name,
        "type": "user_defined_metric_python",
        "project_id": project_id,
        "enabled": enabled,
        "sampling_rate": sampling_rate,
        "code": {
            "metric": inspect.getsource(inspect.getmodule(metric_cls)),
            "arguments": metric_arguments(metric_cls),
        },
    }
