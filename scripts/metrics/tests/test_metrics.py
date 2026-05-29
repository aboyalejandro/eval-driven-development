"""Offline unit tests for code-based metrics — no Opik credentials needed."""

import pytest
from metrics.format_compliance import FormatCompliance
from metrics.registry import ALL_METRICS, build_payload
from metrics.system_prompt_leakage import SystemPromptLeakage
from metrics.tool_call_presence import ToolCallPresence

# --- ToolCallPresence ---


def test_tool_call_presence_json_output():
    m = ToolCallPresence()
    output = {"messages": [{"tool_calls": [{"function": {"name": "search"}}]}]}
    assert m.score("ask", output).value == 1


def test_tool_call_presence_no_tools():
    m = ToolCallPresence()
    assert m.score("ask", "plain text response").value == 0


def test_tool_call_presence_none_output():
    m = ToolCallPresence()
    assert m.score("ask", None).value == 0


def test_tool_call_presence_required_tool_missing():
    m = ToolCallPresence(required_tool="search")
    output = {"messages": [{"tool_calls": [{"function": {"name": "lookup"}}]}]}
    assert m.score("ask", output).value == 0


def test_tool_call_presence_required_tool_present():
    m = ToolCallPresence(required_tool="search")
    output = {"messages": [{"tool_calls": [{"function": {"name": "search"}}]}]}
    assert m.score("ask", output).value == 1


def test_tool_call_presence_metadata_tools_called():
    # Enriched traces carry tools_called in metadata — should take priority over output parsing.
    m = ToolCallPresence()
    assert (
        m.score("ask", "no tools here", metadata={"tools_called": ["search"]}).value
        == 1
    )


def test_tool_call_presence_metadata_required_tool():
    m = ToolCallPresence(required_tool="search")
    assert m.score("ask", None, metadata={"tools_called": ["search"]}).value == 1


def test_tool_call_presence_metadata_required_tool_missing():
    m = ToolCallPresence(required_tool="search")
    assert m.score("ask", None, metadata={"tools_called": ["lookup"]}).value == 0


# --- FormatCompliance ---


def test_format_compliance_valid_json():
    m = FormatCompliance(require_json=True)
    assert m.score("ask", '{"key": "val"}').value == 1


def test_format_compliance_invalid_json():
    m = FormatCompliance(require_json=True)
    assert m.score("ask", "not json").value == 0


def test_format_compliance_pattern_match():
    m = FormatCompliance(pattern=r"Result:")
    assert m.score("ask", "Result: 42").value == 1


def test_format_compliance_pattern_no_match():
    m = FormatCompliance(pattern=r"Result:")
    assert m.score("ask", "nothing here").value == 0


def test_format_compliance_empty_output():
    m = FormatCompliance()
    assert m.score("ask", "").value == 0


def test_format_compliance_dict_output():
    m = FormatCompliance(pattern=r"hello")
    assert m.score("ask", {"content": "hello world"}).value == 1


# --- SystemPromptLeakage ---


def test_system_prompt_leakage_clean():
    m = SystemPromptLeakage()
    assert m.score("ask", "Here is your answer.").value == 1


def test_system_prompt_leakage_system_prompt_tag():
    m = SystemPromptLeakage()
    assert m.score("ask", "See <system_prompt>do this</system_prompt>").value == 0


def test_system_prompt_leakage_internal_tag():
    m = SystemPromptLeakage()
    assert m.score("ask", "Answer: <internal_tools>foo</internal_tools>").value == 0


def test_system_prompt_leakage_custom_pattern():
    m = SystemPromptLeakage(pattern=r"SECRET")
    assert m.score("ask", "Here is SECRET info").value == 0


def test_system_prompt_leakage_none_output():
    m = SystemPromptLeakage()
    assert m.score("ask", None).value == 1


# --- registry ---


def test_build_payload_shape():
    payload = build_payload(ToolCallPresence, project_id="proj-123")
    assert payload["type"] == "user_defined_metric_python"
    assert payload["name"] == "tool_call_presence"
    assert "metric" in payload["code"]
    assert "arguments" in payload["code"]
    assert payload["enabled"] is False
    assert payload["sampling_rate"] == 1.0


def test_all_metrics_have_unique_names():
    names = [cls().name for cls in ALL_METRICS]
    assert len(names) == len(set(names)), "duplicate metric names"
