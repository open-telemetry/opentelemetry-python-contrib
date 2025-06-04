from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

import pytest
from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan

from opentelemetry.semconv._incubating.attributes import (
    event_attributes as EventAttributes,
)

from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes


# span_exporter, log_exporter, chatOpenAI_client, instrument_no_content are coming from
# fixtures defined in conftest.py
@pytest.mark.vcr()
def test_langchain_call(
    span_exporter, log_exporter, metric_reader, chatOpenAI_client, instrument_with_content
):
    llm_model_value = "gpt-3.5-turbo"
    llm = ChatOpenAI(model=llm_model_value)

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    response = llm.invoke(messages)
    assert response.content == "The capital of France is Paris."

    # verify spans
    spans = span_exporter.get_finished_spans()
    print(f"spans: {spans}")
    for span in spans:
        print(f"span: {span}")
        print(f"span attributes: {span.attributes}")
    # TODO: fix the code and ensure the assertions are correct
    assert_openai_completion_attributes(spans[0], llm_model_value, response)

    # verify logs
    logs = log_exporter.get_finished_logs()
    print(f"logs: {logs}")
    for log in logs:
        print(f"log: {log}")
        print(f"log attributes: {log.log_record.attributes}")
        print(f"log body: {log.log_record.body}")
    system_message = {"content": messages[0].content}
    human_message = {"content": messages[1].content}
    assert len(logs) == 3
    assert_message_in_logs(
        logs[0], "gen_ai.system.message", system_message, spans[0]
    )
    assert_message_in_logs(
        logs[1], "gen_ai.user.message", human_message, spans[0]
    )

    chat_generation_event = {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "content": response.content,
            "type": "ChatGeneration"
        }
    }
    assert_message_in_logs(logs[2], "gen_ai.choice", chat_generation_event, spans[0])

    # verify metrics
    metrics = metric_reader.get_metrics_data().resource_metrics
    print(f"metrics: {metrics}")
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    for m in metric_data:
        if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION:
            assert_duration_metric(m, spans[0])
        if m.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE:
            assert_token_usage_metric(m, spans[0])

def assert_openai_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: Optional,
    operation_name: str = "chat",
):
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
    response_model: str = "gpt-3.5-turbo-0125",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "chat",
    span_name: str = "ChatOpenAI.chat",
    system: str = "ChatOpenAI",
    framework: str = "langchain",
):
    assert span.name == span_name
    assert operation_name == span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME]
    assert framework == span.attributes["gen_ai.framework"]
    assert system == span.attributes[gen_ai_attributes.GEN_AI_SYSTEM]
    assert request_model == "gpt-3.5-turbo"
    assert response_model == "gpt-3.5-turbo-0125"
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

def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert log.log_record.attributes[EventAttributes.EVENT_NAME] == event_name
    assert (
        # TODO: use constant from GenAIAttributes.GenAiSystemValues after it is added there
        log.log_record.attributes[gen_ai_attributes.GEN_AI_SYSTEM]
        == "ChatOpenAI"
    )

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == remove_none_values(
            expected_content
        )
    assert_log_parent(log, parent_span)

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

def assert_log_parent(log, span):
    if span:
        assert log.log_record.trace_id == span.get_span_context().trace_id
        assert log.log_record.span_id == span.get_span_context().span_id
        assert (
            log.log_record.trace_flags == span.get_span_context().trace_flags
        )

def assert_duration_metric(metric, parent_span):
    assert metric is not None
    assert len(metric.data.data_points) == 1
    assert metric.data.data_points[0].sum > 0

    assert_duration_metric_attributes(metric.data.data_points[0].attributes, parent_span)
    assert_exemplars(metric.data.data_points[0].exemplars, metric.data.data_points[0].sum, parent_span)

def assert_duration_metric_attributes(attributes, parent_span):
    assert len(attributes) == 5
    assert attributes.get("gen_ai.framework") == "langchain"
    assert attributes.get(gen_ai_attributes.GEN_AI_SYSTEM) == "ChatOpenAI"
    assert attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    assert attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_REQUEST_MODEL
    ]
    assert attributes.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_MODEL
    ]

def assert_token_usage_metric(metric, parent_span):
    assert metric is not None
    assert len(metric.data.data_points) == 2

    assert metric.data.data_points[0].sum > 0
    assert_token_usage_metric_attributes(metric.data.data_points[0].attributes, parent_span)
    assert_exemplars(metric.data.data_points[0].exemplars, metric.data.data_points[0].sum, parent_span)

    assert metric.data.data_points[1].sum > 0
    assert_token_usage_metric_attributes(metric.data.data_points[1].attributes, parent_span)
    assert_exemplars(metric.data.data_points[1].exemplars, metric.data.data_points[1].sum, parent_span)

def assert_token_usage_metric_attributes(attributes, parent_span):
    assert len(attributes) == 6
    assert attributes.get("gen_ai.framework") == "langchain"
    assert attributes.get(gen_ai_attributes.GEN_AI_SYSTEM) == "ChatOpenAI"
    assert attributes.get(gen_ai_attributes.GEN_AI_OPERATION_NAME) == gen_ai_attributes.GenAiOperationNameValues.CHAT.value
    assert attributes.get(gen_ai_attributes.GEN_AI_REQUEST_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_REQUEST_MODEL
    ]
    assert attributes.get(gen_ai_attributes.GEN_AI_RESPONSE_MODEL) == parent_span.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_MODEL
    ]

def assert_exemplars(exemplars, sum, parent_span):
    assert len(exemplars) == 1
    assert exemplars[0].value == sum
    assert exemplars[0].span_id == parent_span.get_span_context().span_id
    assert exemplars[0].trace_id == parent_span.get_span_context().trace_id

