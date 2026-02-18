from typing import Optional

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from openai import AuthenticationError

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    event_attributes as EventAttributes,
)
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import error_attributes


# span_exporter, metric_reader, log_exporter, start_instrumentation, chat_openai_gpt_3_5_turbo_model are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
@pytest.mark.parametrize(
    "capture_content",
    ["SPAN_ONLY", "NO_CONTENT", "SPAN_AND_EVENT", "EVENT_ONLY"],
)
def test_chat_openai_gpt_3_5_turbo_model_llm_call(
    span_exporter,
    metric_reader,
    log_exporter,
    start_instrumentation,
    chat_openai_gpt_3_5_turbo_model,
    monkeypatch,
    capture_content,
):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture_content
    )

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    response = chat_openai_gpt_3_5_turbo_model.invoke(messages)
    assert response.content == "The capital of France is Paris."

    # verify spans
    spans = span_exporter.get_finished_spans()

    verify_content: bool = (
        True if capture_content in ("SPAN_ONLY", "SPAN_AND_EVENT") else False
    )
    assert_openai_completion_attributes(
        spans[0] if len(spans) > 0 else None,
        response,
        verify_content=verify_content,
    )

    # verify metrics
    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    resource_metrics = metrics_data.resource_metrics
    assert resource_metrics is not None
    assert len(resource_metrics) == 1

    metrics = resource_metrics[0].scope_metrics[0].metrics
    assert len(metrics) == 2
    for metric in metrics:
        if metric.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION:
            assert_duration_metric(metric, spans[0])
        if metric.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE:
            assert_token_usage_metric(metric, spans[0])

    # verify logs
    logs = log_exporter.get_finished_logs()
    if capture_content in ("SPAN_AND_EVENT", "EVENT_ONLY"):
        assert len(logs) == 1
        log_record = logs[0].log_record
        assert_log_record(log_record, spans[0])
    elif capture_content in ("SPAN_ONLY", "NO_CONTENT"):
        assert len(logs) == 0


# span_exporter, metric_reader, log_exporter, start_instrumentation, chat_openai_gpt_3_5_turbo_model are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
@pytest.mark.parametrize(
    "capture_content",
    ["SPAN_ONLY", "NO_CONTENT", "SPAN_AND_EVENT", "EVENT_ONLY"],
)
def test_chat_openai_gpt_3_5_turbo_model_llm_call_with_error(
    span_exporter,
    metric_reader,
    log_exporter,
    start_instrumentation,
    chat_openai_gpt_3_5_turbo_model,
    monkeypatch,
    capture_content,
):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture_content
    )

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    response = None
    try:
        response = chat_openai_gpt_3_5_turbo_model.invoke(messages)
    except Exception as e:
        # For this test, to get error, cassettes were recorded with no OPENAI_API_KEY, so an error is expected here.
        assert isinstance(e, AuthenticationError)

    assert response is None

    # verify spans
    spans = span_exporter.get_finished_spans()

    verify_content: bool = (
        True if capture_content in ("SPAN_ONLY", "SPAN_AND_EVENT") else False
    )
    assert_openai_completion_attributes_with_error(
        spans[0] if len(spans) > 0 else None, verify_content=verify_content
    )

    # verify metrics
    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    resource_metrics = metrics_data.resource_metrics
    assert len(resource_metrics) == 1
    metrics = resource_metrics[0].scope_metrics[0].metrics
    assert len(metrics) == 1
    assert metrics[0].name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    assert_duration_metric_when_error(metrics[0], spans[0])

    # verify logs
    logs = log_exporter.get_finished_logs()
    if capture_content in ("SPAN_AND_EVENT", "EVENT_ONLY"):
        assert len(logs) == 1
        log_record = logs[0].log_record
        assert_log_record_when_error(log_record, spans[0])
    elif capture_content in ("SPAN_ONLY", "NO_CONTENT"):
        assert len(logs) == 0


# span_exporter, start_instrumentation, us_amazon_nova_lite_v1_0 are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
def test_us_amazon_nova_lite_v1_0_bedrock_llm_call(
    span_exporter, start_instrumentation, us_amazon_nova_lite_v1_0
):
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = us_amazon_nova_lite_v1_0.invoke(messages)

    assert result.content.find("The capital of France is Paris") != -1

    # verify spans
    spans = span_exporter.get_finished_spans()
    print(f"spans: {spans}")
    for span in spans:
        print(f"span: {span}")
        print(f"span attributes: {span.attributes}")
    # TODO: fix the code and ensure the assertions are correct
    assert_bedrock_completion_attributes(spans[0], result)


# span_exporter, start_instrumentation, gemini are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
def test_gemini(span_exporter, start_instrumentation, gemini):
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = gemini.invoke(messages)

    assert result.content.find("The capital of France is **Paris**") != -1

    # verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0  # No spans should be created for gemini as of now


def assert_openai_completion_attributes(
    span: ReadableSpan, response: Optional, verify_content: bool = True
):
    assert span is not None
    attributes = span.attributes
    assert span.name == "chat gpt-3.5-turbo"
    assert attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    assert (
        attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL] == "gpt-3.5-turbo"
    )
    assert (
        attributes[gen_ai_attributes.GEN_AI_RESPONSE_MODEL]
        == "gpt-3.5-turbo-0125"
    )
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE] == 0.1
    assert attributes["gen_ai.provider.name"] == "openai"
    assert gen_ai_attributes.GEN_AI_RESPONSE_ID in attributes
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert (
        attributes[gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.5
    )
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.5
    stop_sequences = attributes.get(
        gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES
    )
    assert all(seq in ["\n", "Human:", "AI:"] for seq in stop_sequences)
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_SEED] == 100

    input_tokens = response.response_metadata.get("token_usage").get(
        "prompt_tokens"
    )
    if input_tokens:
        assert (
            input_tokens
            == attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in attributes

    output_tokens = response.response_metadata.get("token_usage").get(
        "completion_tokens"
    )
    if output_tokens:
        assert (
            output_tokens
            == attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in attributes

    if verify_content:
        input_message = attributes[gen_ai_attributes.GEN_AI_INPUT_MESSAGES]
        assert input_message is not None
        assert '"role":"system"' in input_message
        assert '"content":"You are a helpful assistant!"' in input_message
        assert '"role":"human"' in input_message
        assert '"content":"What is the capital of France?"' in input_message

        # Assert output message
        output_message = attributes[gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES]
        assert output_message is not None
        assert '"role":"ai"' in output_message
        assert '"content":"The capital of France is Paris."' in output_message
        assert '"finish_reason":"stop"' in output_message
    else:
        assert gen_ai_attributes.GEN_AI_INPUT_MESSAGES not in attributes
        assert gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES not in attributes


def assert_openai_completion_attributes_with_error(
    span: ReadableSpan, verify_content: bool = True
):
    assert span is not None
    assert span.name == "chat gpt-3.5-turbo"
    attributes = span.attributes
    assert attributes[error_attributes.ERROR_TYPE] == "AuthenticationError"
    assert attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    assert (
        attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL] == "gpt-3.5-turbo"
    )
    assert gen_ai_attributes.GEN_AI_RESPONSE_MODEL not in attributes
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE] == 0.1
    assert attributes["gen_ai.provider.name"] == "openai"
    assert gen_ai_attributes.GEN_AI_RESPONSE_ID not in attributes
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert (
        attributes[gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.5
    )
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.5
    stop_sequences = attributes.get(
        gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES
    )
    assert all(seq in ["\n", "Human:", "AI:"] for seq in stop_sequences)
    assert attributes[gen_ai_attributes.GEN_AI_REQUEST_SEED] == 100

    assert gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in attributes

    assert gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in attributes

    if verify_content:
        input_message = attributes[gen_ai_attributes.GEN_AI_INPUT_MESSAGES]
        assert input_message is not None
        assert '"role":"system"' in input_message
        assert '"content":"You are a helpful assistant!"' in input_message
        assert '"role":"human"' in input_message
        assert '"content":"What is the capital of France?"' in input_message

        # Assert output message
        assert gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES not in attributes
    else:
        assert gen_ai_attributes.GEN_AI_INPUT_MESSAGES not in attributes
        assert gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES not in attributes


def assert_bedrock_completion_attributes(
    span: ReadableSpan, response: Optional
):
    assert span.name == "chat us.amazon.nova-lite-v1:0"
    assert span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    assert (
        span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
        == "us.amazon.nova-lite-v1:0"
    )

    assert span.attributes["gen_ai.provider.name"] == "amazon_bedrock"
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE] == 0.1

    input_tokens = response.usage_metadata.get("input_tokens")
    if input_tokens:
        assert (
            input_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
        )

    output_tokens = response.usage_metadata.get("output_tokens")
    if output_tokens:
        assert (
            output_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )


def assert_duration_metric(metric, parent_span):
    assert metric is not None
    assert len(metric.data.data_points) == 1
    assert metric.data.data_points[0].sum > 0

    assert_duration_metric_attributes(
        metric.data.data_points[0].attributes, parent_span
    )
    assert_exemplars(
        metric.data.data_points[0].exemplars,
        metric.data.data_points[0].sum,
        parent_span,
    )


def assert_duration_metric_attributes(attributes, parent_span):
    assert len(attributes) == 4
    assert attributes.get(gen_ai_attributes.GEN_AI_PROVIDER_NAME) == "openai"
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME)
        == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    )
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL)
        == parent_span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
    )
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL)
        == parent_span.attributes[gen_ai_attributes.GEN_AI_RESPONSE_MODEL]
    )


def assert_duration_metric_when_error(metric, parent_span):
    assert metric is not None
    assert len(metric.data.data_points) == 1
    assert metric.data.data_points[0].sum > 0

    assert_duration_metric_attributes_when_error(
        metric.data.data_points[0].attributes, parent_span
    )
    assert_exemplars(
        metric.data.data_points[0].exemplars,
        metric.data.data_points[0].sum,
        parent_span,
    )


def assert_duration_metric_attributes_when_error(attributes, parent_span):
    assert len(attributes) == 4
    assert attributes[error_attributes.ERROR_TYPE] == "AuthenticationError"
    assert attributes.get(gen_ai_attributes.GEN_AI_PROVIDER_NAME) == "openai"
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME)
        == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    )
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL)
        == parent_span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
    )


def assert_token_usage_metric(metric, parent_span):
    assert metric is not None
    assert len(metric.data.data_points) == 2

    assert metric.data.data_points[0].sum > 0
    assert_token_usage_metric_attributes(
        metric.data.data_points[0].attributes, parent_span, "input"
    )
    assert_exemplars(
        metric.data.data_points[0].exemplars,
        metric.data.data_points[0].sum,
        parent_span,
    )

    assert metric.data.data_points[1].sum > 0
    assert_token_usage_metric_attributes(
        metric.data.data_points[1].attributes, parent_span, "output"
    )
    assert_exemplars(
        metric.data.data_points[1].exemplars,
        metric.data.data_points[1].sum,
        parent_span,
    )


def assert_token_usage_metric_attributes(attributes, parent_span, token_type):
    assert len(attributes) == 5
    assert attributes.get(gen_ai_attributes.GEN_AI_PROVIDER_NAME) == "openai"
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME)
        == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    )
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL)
        == parent_span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
    )
    assert (
        attributes.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL)
        == parent_span.attributes[gen_ai_attributes.GEN_AI_RESPONSE_MODEL]
    )
    assert attributes.get(gen_ai_attributes.GEN_AI_TOKEN_TYPE) == token_type


def assert_exemplars(exemplars, sum, parent_span):
    assert len(exemplars) == 1
    assert exemplars[0].value == sum
    assert exemplars[0].span_id == parent_span.get_span_context().span_id
    assert exemplars[0].trace_id == parent_span.get_span_context().trace_id


def assert_log_record(log_record, parent_span):
    # Event name (support both .event_name and attributes for SDK differences)
    event_name = getattr(
        log_record, "event_name", None
    ) or log_record.attributes.get(EventAttributes.EVENT_NAME)
    assert event_name == "gen_ai.client.inference.operation.details"

    attrs = log_record.attributes
    assert attrs.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == "chat"
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL) == "gpt-3.5-turbo"
    assert attrs.get(gen_ai_attributes.GEN_AI_PROVIDER_NAME) == "openai"
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE) == 0.1
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_TOP_P) == 0.9
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY) == 0.5
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY) == 0.5
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS) == 100
    stop_seqs = _normalize_to_list(
        attrs.get(gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES, [])
    )
    assert stop_seqs == ["\n", "Human:", "AI:"]
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_SEED) == 100
    assert attrs.get(gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS) == (
        "stop",
    )
    assert (
        attrs.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL)
        == "gpt-3.5-turbo-0125"
    )
    assert gen_ai_attributes.GEN_AI_RESPONSE_ID in attrs
    assert attrs.get(gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS) == 24
    assert attrs.get(gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS) == 7

    # Input/output messages: normalize list/tuple and compare structure
    input_msgs = _normalize_to_list(
        attrs.get(gen_ai_attributes.GEN_AI_INPUT_MESSAGES, [])
    )
    expected_input = [
        {
            "parts": [
                {"content": "You are a helpful assistant!", "type": "text"}
            ],
            "role": "system",
        },
        {
            "parts": [
                {"content": "What is the capital of France?", "type": "text"}
            ],
            "role": "human",
        },
    ]
    assert len(input_msgs) == 2
    for i, exp in enumerate(expected_input):
        got = _normalize_to_dict(input_msgs[i])
        assert got["role"] == exp["role"]
        assert _normalize_to_list(got["parts"]) == exp["parts"]

    output_msgs = _normalize_to_list(
        attrs.get(gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES, [])
    )
    assert len(output_msgs) == 1
    out = _normalize_to_dict(output_msgs[0])
    assert out["role"] == "ai"
    assert out["finish_reason"] == "stop"
    assert _normalize_to_list(out["parts"]) == [
        {"content": "The capital of France is Paris.", "type": "text"}
    ]
    assert_log_parent(log_record, parent_span)


def assert_log_record_when_error(log_record, parent_span):
    # Event name (support both .event_name and attributes for SDK differences)
    event_name = getattr(
        log_record, "event_name", None
    ) or log_record.attributes.get(EventAttributes.EVENT_NAME)
    assert event_name == "gen_ai.client.inference.operation.details"

    attrs = log_record.attributes
    assert attrs.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == "chat"
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL) == "gpt-3.5-turbo"
    assert attrs.get(gen_ai_attributes.GEN_AI_PROVIDER_NAME) == "openai"
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE) == 0.1
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_TOP_P) == 0.9
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY) == 0.5
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY) == 0.5
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS) == 100
    stop_seqs = _normalize_to_list(
        attrs.get(gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES, [])
    )
    assert stop_seqs == ["\n", "Human:", "AI:"]
    assert attrs.get(gen_ai_attributes.GEN_AI_REQUEST_SEED) == 100
    assert gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS not in attrs
    assert gen_ai_attributes.GEN_AI_RESPONSE_MODEL not in attrs
    assert gen_ai_attributes.GEN_AI_RESPONSE_ID not in attrs
    assert gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in attrs
    assert gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in attrs

    # Input/output messages: normalize list/tuple and compare structure
    input_msgs = _normalize_to_list(
        attrs.get(gen_ai_attributes.GEN_AI_INPUT_MESSAGES, [])
    )
    expected_input = [
        {
            "parts": [
                {"content": "You are a helpful assistant!", "type": "text"}
            ],
            "role": "system",
        },
        {
            "parts": [
                {"content": "What is the capital of France?", "type": "text"}
            ],
            "role": "human",
        },
    ]
    assert len(input_msgs) == 2
    for i, exp in enumerate(expected_input):
        got = _normalize_to_dict(input_msgs[i])
        assert got["role"] == exp["role"]
        assert _normalize_to_list(got["parts"]) == exp["parts"]

    assert gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES not in attrs
    assert_log_parent(log_record, parent_span)


def _normalize_to_list(value):
    """Normalize tuple or list to list for OpenTelemetry compatibility."""
    return list(value) if isinstance(value, tuple) else value


def _normalize_to_dict(value):
    """Normalize tuple or dict to dict for OpenTelemetry compatibility."""
    return dict(value) if isinstance(value, tuple) else value


def assert_log_parent(log_record, span):
    if span:
        assert log_record.trace_id == span.get_span_context().trace_id
        assert log_record.span_id == span.get_span_context().span_id
        assert log_record.trace_flags == span.get_span_context().trace_flags
