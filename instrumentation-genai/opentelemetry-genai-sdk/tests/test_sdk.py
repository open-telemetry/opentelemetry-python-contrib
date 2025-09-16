import pytest
from opentelemetry.genai.sdk.api import (
    llm_start, llm_stop, llm_fail,
    tool_start, tool_stop, tool_fail,
)
from opentelemetry.genai.sdk.evals import get_evaluator, EvaluationResult
from opentelemetry.genai.sdk.exporters import SpanMetricEventExporter, SpanMetricExporter

@pytest.fixture
def sample_llm_invocation():
    run_id = llm_start("test-model", "hello world", custom_attr="value")
    invocation = llm_stop(run_id, response="hello back", extra="info")
    return invocation

@pytest.fixture
def sample_tool_invocation():
    run_id = tool_start("test-tool", {"input": 123}, flag=True)
    invocation = tool_stop(run_id, output={"output": "ok"}, status="done")
    return invocation

def test_llm_start_and_stop(sample_llm_invocation):
    inv = sample_llm_invocation
    assert inv.model_name == "test-model"
    assert inv.prompt == "hello world"
    assert inv.response == "hello back"
    assert inv.attributes.get("custom_attr") == "value"
    assert inv.attributes.get("extra") == "info"
    assert inv.end_time >= inv.start_time

def test_tool_start_and_stop(sample_tool_invocation):
    inv = sample_tool_invocation
    assert inv.tool_name == "test-tool"
    assert inv.input == {"input": 123}
    assert inv.output == {"output": "ok"}
    assert inv.attributes.get("flag") is True
    assert inv.attributes.get("status") == "done"
    assert inv.end_time >= inv.start_time

@pytest.mark.parametrize("name,method", [
    ("deepevals", "deepevals"),
    ("openlit", "openlit"),
])
def test_evaluator_factory(name, method, sample_llm_invocation):
    evaluator = get_evaluator(name)
    result = evaluator.evaluate(sample_llm_invocation)
    assert isinstance(result, EvaluationResult)
    assert result.details.get("method") == method

def test_exporters_no_error(sample_llm_invocation):
    event_exporter = SpanMetricEventExporter()
    metric_exporter = SpanMetricExporter()
    event_exporter.export(sample_llm_invocation)
    metric_exporter.export(sample_llm_invocation)

def test_llm_fail():
    run_id = llm_start("fail-model", "prompt")
    inv = llm_fail(run_id, error="something went wrong")
    assert inv.attributes.get("error") == "something went wrong"
    assert inv.end_time is not None

def test_tool_fail():
    run_id = tool_start("fail-tool", {"x": 1})
    inv = tool_fail(run_id, error="tool error")
    assert inv.attributes.get("error") == "tool error"
    assert inv.end_time is not None
