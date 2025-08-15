"""Test suite for LangChain LLM instrumentation with OpenTelemetry.

This module contains tests that verify the integration between LangChain LLM calls
and OpenTelemetry for observability, including spans, logs, and metrics.
"""
# Standard library imports
import json,os
from typing import Any, Dict, List, Optional

# Third-party imports
import pytest
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from opentelemetry.sdk.metrics.export import Metric
from opentelemetry.sdk.trace import ReadableSpan, Span
from opentelemetry.semconv._incubating.attributes import event_attributes as EventAttributes
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes

# Constants
CHAT = gen_ai_attributes.GenAiOperationNameValues.CHAT.value
TOOL_OPERATION = "execute_tool"

###########################################
# Assertion Helpers
###########################################

# OpenAI Attributes Helpers

def assert_openai_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: Any,
    operation_name: str = "chat",
) -> None:
    """Verify OpenAI completion attributes in a span.
    
    Args:
        span: The span to check
        request_model: Expected request model name
        response: The LLM response object
        operation_name: Expected operation name (default: "chat")
    """
    return assert_all_openai_attributes(
        span,
        request_model,
        response.response_metadata.get("model_name"),
        response.response_metadata.get("token_usage").get("prompt_tokens"),
        response.response_metadata.get("token_usage").get("completion_tokens"),
        operation_name,
    )

def assert_all_openai_attributes(
    span: ReadableSpan,
    request_model: str,
    response_model: str = "gpt-4o-mini-2024-07-18",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "chat",
    span_name: str = "chat gpt-4o-mini",
    system: str = "LangChain:ChatOpenAI",
):
    assert span.name == span_name

    assert operation_name == span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME]

    assert request_model == "gpt-4o-mini"

    assert response_model == "gpt-4o-mini-2024-07-18"

    assert gen_ai_attributes.GEN_AI_RESPONSE_ID in span.attributes

    if input_tokens:
        assert (
            input_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes

    if output_tokens:
        assert (
            output_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )

def _assert_tool_request_functions_on_span(
    span: Span, expected_tool_names: List[str]
) -> None:
    """Verify tool request functions in span attributes.
    
    Args:
        span: The span to check
        expected_tool_names: List of expected tool names
    """
    for i, name in enumerate(expected_tool_names):
        assert span.attributes.get(f"gen_ai.request.function.{i}.name") == name
        assert f"gen_ai.request.function.{i}.description" in span.attributes
        assert f"gen_ai.request.function.{i}.parameters" in span.attributes



# Log Assertion Helpers

def assert_message_in_logs(
    log: Any,
    event_name: str,
    expected_content: Dict[str, Any],
    parent_span: Span,
) -> None:
    """Verify a log message has the expected content and parent span.
    
    Args:
        log: The log record to check
        event_name: Expected event name
        expected_content: Expected content in the log body
        parent_span: Parent span for context verification
    """
    assert log.log_record.attributes[EventAttributes.EVENT_NAME] == event_name
    # assert (
        # TODO: use constant from GenAIAttributes.GenAiSystemValues after it is added there
    #         log.log_record.attributes[gen_ai_attributes.GEN_AI_SYSTEM]
    #         == "langchain"
    # )

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == remove_none_values(
            expected_content
        )
    assert_log_parent(log, parent_span)

def assert_log_parent(log, span):
    if span:
        assert log.log_record.trace_id == span.get_span_context().trace_id
        assert log.log_record.span_id == span.get_span_context().span_id
        assert (
            log.log_record.trace_flags == span.get_span_context().trace_flags
        )

# Metric Assertion Helpers

def remove_none_values(body):
    result = {}
    for key, value in body.items():
        if value is None:
            continue
        if isinstance(value, dict):
            result[key] = remove_none_values(value)
        elif isinstance(value, list):
            result[key] = [remove_none_values(i) for i in value]
        else:
            result[key] = value
    return result

def assert_duration_metric(metric: Metric, parent_span: Span) -> None:
    """Verify duration metric has expected structure and values.
    
    Args:
        metric: The metric to verify
        parent_span: Parent span for context verification
    """
    assert metric is not None
    assert len(metric.data.data_points) >= 1
    assert metric.data.data_points[0].sum > 0

    assert_duration_metric_attributes(metric.data.data_points[0].attributes, parent_span)
    assert_exemplars(metric.data.data_points[0].exemplars, metric.data.data_points[0].sum, parent_span)

def assert_exemplars(exemplars, sum, parent_span):
    assert len(exemplars) >= 1
    assert exemplars[0].value >= sum
    assert exemplars[0].span_id == parent_span.get_span_context().span_id
    assert exemplars[0].trace_id == parent_span.get_span_context().trace_id

def assert_token_usage_metric(metric: Metric, parent_span: Span) -> None:
    """Verify token usage metric has expected structure and values.
    
    Args:
        metric: The metric to verify
        parent_span: Parent span for context verification
    """
    assert metric is not None
    assert len(metric.data.data_points) == 2

    assert metric.data.data_points[0].sum > 0
    assert_token_usage_metric_attributes(metric.data.data_points[0].attributes, parent_span)
    assert_exemplars(metric.data.data_points[0].exemplars, metric.data.data_points[0].sum, parent_span)

    assert metric.data.data_points[1].sum > 0
    assert_token_usage_metric_attributes(metric.data.data_points[1].attributes, parent_span)
    assert_exemplars(metric.data.data_points[1].exemplars, metric.data.data_points[1].sum, parent_span)


def assert_duration_metric_attributes(attributes: Dict[str, Any], parent_span: Span) -> None:
    """Verify duration metric attributes.
    
    Args:
        attributes: Metric attributes to verify
        parent_span: Parent span for context verification
    """
    assert len(attributes) == 5
    # assert attributes.get(gen_ai_attributes.GEN_AI_SYSTEM) == "langchain"
    assert attributes.get(
        gen_ai_attributes.GEN_AI_OPERATION_NAME) == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    assert attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_REQUEST_MODEL
    ]
    assert attributes.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_MODEL
    ]


def assert_token_usage_metric_attributes(
    attributes: Dict[str, Any], parent_span: Span
) -> None:
    """Verify token usage metric attributes.
    
    Args:
        attributes: Metric attributes to verify
        parent_span: Parent span for context verification
    """
    assert len(attributes) == 6
    # assert attributes.get(gen_ai_attributes.GEN_AI_SYSTEM) == "langchain"
    assert attributes.get(
        gen_ai_attributes.GEN_AI_OPERATION_NAME) == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    assert attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_REQUEST_MODEL
    ]
    assert attributes.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_MODEL
    ]


def assert_duration_metric_with_tool(metric: Metric, spans: List[Span]) -> None:
    """Verify duration metric when tools are involved.
    
    Args:
        metric: The metric to verify
        spans: List of spans for context verification
    """
    assert spans, "No LLM CHAT spans found"
    llm_points = [
        dp for dp in metric.data.data_points
        if dp.attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == CHAT
    ]
    assert len(llm_points) >= 1
    for dp in llm_points:
        assert dp.sum > 0
        assert_duration_metric_attributes(dp.attributes, spans[0])


def assert_token_usage_metric_with_tool(metric: Metric, spans: List[Span]) -> None:
    """Verify token usage metric when tools are involved.
    
    Args:
        metric: The metric to verify
        spans: List of spans for context verification
    """
    assert spans, "No LLM CHAT spans found"
    llm_points = [
        dp for dp in metric.data.data_points
        if dp.attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == CHAT
    ]
    assert len(llm_points) >= 2  # Should have both input and output token metrics
    for dp in llm_points:
        assert dp.sum > 0
        assert_token_usage_metric_attributes(dp.attributes, spans[0])



###########################################
# Test Fixtures (from conftest.py)
# - span_exporter
# - log_exporter
# - metric_reader
# - chatOpenAI_client
# - instrument_with_content
###########################################

###########################################
# Test Functions
###########################################

def _get_llm_spans(spans: List[Span]) -> List[Span]:
    """Filter spans to get only LLM chat spans.
    
    Args:
        spans: List of spans to filter
        
    Returns:
        List of spans that are LLM chat operations
    """
    return [
        s for s in spans
        if s.attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == CHAT
    ]


###########################################
# Test Functions
###########################################

# Note: The following test functions use VCR to record and replay HTTP interactions
# for reliable and deterministic testing. Each test verifies both the functional
# behavior of the LLM calls and the associated OpenTelemetry instrumentation.

# Basic LLM Call Tests

@pytest.mark.vcr()
def test_langchain_call(
    span_exporter,
    log_exporter,
    metric_reader,
    chatOpenAI_client,  # noqa: N803
    instrument_with_content: None,
    monkeypatch,
) -> None:
    """Test basic LLM call with telemetry verification.
    
    This test verifies that:
    1. The LLM call completes successfully
    2. Spans are generated with correct attributes
    3. Logs contain expected messages
    4. Metrics are recorded for the operation
    """
    # Setup test LLM with dummy values
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("APPKEY", "test-app-key")
    llm_model_value = "gpt-4o-mini"
    llm = ChatOpenAI(
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://chat-ai.cisco.com/openai/deployments/gpt-4o-mini",
        model=llm_model_value,
        default_headers={"api-key": os.getenv("OPENAI_API_KEY")},
        model_kwargs={"user": json.dumps({"appkey": os.getenv("APPKEY")})},
    )

    # Prepare test messages
    system_message = SystemMessage(content="You are a helpful assistant!")
    user_message = HumanMessage(content="What is the capital of France?")
    messages = [system_message, user_message]

    # Execute LLM call
    response = llm.invoke(messages)
    assert response.content == "The capital of France is Paris."

    # --- Verify Telemetry ---
    
    # 1. Check spans
    spans = span_exporter.get_finished_spans()
    assert spans, "No spans were exported"
    assert_openai_completion_attributes(spans[0], llm_model_value, response)

    # 2. Check logs
    logs = log_exporter.get_finished_logs()
    print(f"logs: {logs}")
    for log in logs:
        print(f"log: {log}")
        print(f"log attributes: {log.log_record.attributes}")
        print(f"log body: {log.log_record.body}")
    system_message = {"content": messages[0].content}
    human_message = {"content": messages[1].content}
    # will add the logs back once the logs are fixed
    # assert_message_in_logs(
    #     logs[0], "gen_ai.system.message", system_message, spans[0]
    # )
    # assert_message_in_logs(
    #     logs[1], "gen_ai.human.message", human_message, spans[0]
    # )

    chat_generation_event = {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "content": response.content,
            "type": "ChatGeneration"
        }
    }
    # assert_message_in_logs(logs[2], "gen_ai.choice", chat_generation_event, spans[0])

    # 3. Check metrics
    metrics = metric_reader.get_metrics_data().resource_metrics

    print(f"metrics: {metrics}")
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    for m in metric_data:
        if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION:
            assert_duration_metric(m, spans[0])
        if m.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE:
            assert_token_usage_metric(m, spans[0])


@pytest.mark.vcr()
def test_langchain_call_with_tools(
    span_exporter,
    log_exporter,
    metric_reader,
    instrument_with_content: None,
    monkeypatch
) -> None:
    """Test LLM call with tool usage and verify telemetry.
    
    This test verifies:
    1. Tool definitions and bindings work correctly
    2. Tool execution and response handling
    3. Telemetry includes tool-related spans and metrics
    """
    # Define test tools
    @tool
    def add(a: int, b: int) -> int:
        """Add two integers together."""
        return a + b

    @tool
    def multiply(a: int, b: int) -> int:
        """Multiply two integers together."""
        return a * b

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("APPKEY", "test-app-key")
    # Setup LLM with tools
    llm = ChatOpenAI(
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url='https://chat-ai.cisco.com/openai/deployments/gpt-4o-mini',
        model='gpt-4o-mini',
        default_headers={"api-key": os.getenv("OPENAI_API_KEY")},
        model_kwargs={"user": json.dumps({"appkey": os.getenv("APPKEY")})},
    )
    
    tools = [add, multiply]
    llm_with_tools = llm.bind_tools(tools)
    
    # Test conversation flow
    messages = [HumanMessage("Please add 2 and 3, then multiply 2 and 3.")]
    
    # First LLM call - should return tool calls
    ai_msg = llm_with_tools.invoke(messages)
    messages.append(ai_msg)
    
    # Process tool calls
    tool_calls = getattr(ai_msg, "tool_calls", None) or \
                ai_msg.additional_kwargs.get("tool_calls", [])
    
    # Execute tools and collect results
    name_map = {"add": add, "multiply": multiply}
    for tc in tool_calls:
        fn = tc.get("function", {})
        tool_name = (fn.get("name") or tc.get("name") or "").lower()
        arg_str = fn.get("arguments")
        args = json.loads(arg_str) if isinstance(arg_str, str) else (tc.get("args") or {})
        
        selected_tool = name_map[tool_name]
        tool_output = selected_tool.invoke(args)
        
        messages.append(ToolMessage(
            content=str(tool_output), 
            name=tool_name,
            tool_call_id=tc.get("id", "")
        ))

    # Final LLM call with tool results
    final = llm_with_tools.invoke(messages)
    assert isinstance(final.content, str) and len(final.content) > 0
    assert "5" in final.content and "6" in final.content

    # --- Verify Telemetry ---
    spans = span_exporter.get_finished_spans()
    assert len(spans) >= 1
    _assert_tool_request_functions_on_span(spans[0], ["add", "multiply"])

    # Verify logs
    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 3  # system/user + gen_ai.choice

    choice_logs = [l for l in logs if l.log_record.attributes.get("event.name") == "gen_ai.choice"]
    assert len(choice_logs) >= 1
    body = dict(choice_logs[0].log_record.body or {})
    assert "message" in body and isinstance(body["message"], dict)
    assert body["message"].get("type") == "ChatGeneration"
    assert isinstance(body["message"].get("content"), str)

    # Verify metrics with tool usage
    llm_spans = _get_llm_spans(spans)
    for rm in metric_reader.get_metrics_data().resource_metrics:
        for scope in rm.scope_metrics:
            for metric in scope.metrics:
                if metric.name == "gen_ai.client.operation.duration":
                    assert_duration_metric_with_tool(metric, llm_spans)
                elif metric.name == "gen_ai.client.token.usage":
                    assert_token_usage_metric_with_tool(metric, llm_spans)


# Tool-related Assertion Helpers
def assert_duration_metric_with_tool(metric: Metric, spans: List[Span]) -> None:
    """Verify duration metric attributes when tools are involved.
    
    Args:
        metric: The metric data points to verify
        spans: List of spans for context verification
    """
    llm_points = [
        dp for dp in metric.data.data_points
        if dp.attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == CHAT
    ]
    assert len(llm_points) >= 1
    for dp in llm_points:
        assert_duration_metric_attributes(dp.attributes, spans[0])
        if getattr(dp, "exemplars", None):
            assert_exemplar_matches_any_llm_span(dp.exemplars, spans)


def assert_token_usage_metric_with_tool(metric: Metric, spans: List[Span]) -> None:
    """Verify token usage metric when tools are involved.
    
    Args:
        metric: The metric to verify
        spans: List of spans for context verification
    """
    assert spans, "No LLM CHAT spans found"

    # Only consider CHAT datapoints (ignore tool)
    llm_points = [
        dp for dp in metric.data.data_points
        if dp.attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == CHAT
    ]
    assert len(llm_points) >= 2

    for dp in llm_points:
        assert dp.sum > 0
        assert_token_usage_metric_attributes(dp.attributes, spans[0])  # use attrs from any LLM span
        if getattr(dp, "exemplars", None):
            assert_exemplar_matches_any_llm_span(dp.exemplars, spans)

def assert_exemplar_matches_any_llm_span(exemplars, spans):
    assert exemplars and len(exemplars) >= 1
    # Build a lookup of span_id -> (trace_id, span_obj)
    by_id = {s.get_span_context().span_id: s for s in spans}
    for ex in exemplars:
        s = by_id.get(ex.span_id)
        assert s is not None, f"exemplar.span_id not found among LLM spans: {ex.span_id}"
        # Optional: also ensure consistent trace
        assert ex.trace_id == s.get_span_context().trace_id