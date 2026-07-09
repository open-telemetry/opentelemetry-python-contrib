# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the AWS Bedrock instrumentation.

These tests never touch the network. bedrock-runtime clients are constructed
with static credentials (which does not perform any I/O) and driven with
``botocore.stub.Stubber`` so the real ``botocore`` request/response
serialization runs against canned data.

The instrumentor is enabled *before* each client is created so that the
``create_client`` wrapper installs the method wrappers on the client instance.

The tests exercise the latest-experimental semantic-convention path
(``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental``), which is what
the ``instrument`` fixtures enable.
"""

import io
import json

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)

GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
AWS_BEDROCK = "aws.bedrock"
TEST_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"

CONVERSE_MESSAGES = [{"role": "user", "content": [{"text": "hello"}]}]


def _make_client():
    return boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="x",
        aws_secret_access_key="x",
    )


def _converse_response():
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "This is a test"}],
            }
        },
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": 10,
            "outputTokens": 5,
            "totalTokens": 15,
        },
        "metrics": {"latencyMs": 42},
    }


def _anthropic_invoke_body():
    return json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hello"}],
        }
    )


def _anthropic_invoke_response_body():
    payload = json.dumps(
        {
            "id": "msg_test_123",
            "role": "assistant",
            "content": [{"type": "text", "text": "This is a test"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }
    ).encode("utf-8")
    return payload


def _get_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def _get_metric(metric_reader, name):
    metrics_data = metric_reader.get_metrics_data()
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return metric
    return None


def _assert_common_request_attributes(span, operation):
    assert span.name == f"{operation} {TEST_MODEL}"
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == operation
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == AWS_BEDROCK
    assert isinstance(span.attributes[GEN_AI_PROVIDER_NAME], str)
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == TEST_MODEL
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str
    )


def _assert_token_usage_metric(metric_reader):
    token_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    assert token_metric is not None
    token_types = {
        point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
        for point in token_metric.data.data_points
    }
    assert GenAIAttributes.GenAiTokenTypeValues.INPUT.value in token_types
    assert GenAIAttributes.GenAiTokenTypeValues.OUTPUT.value in token_types
    for point in token_metric.data.data_points:
        assert point.attributes[GEN_AI_PROVIDER_NAME] == AWS_BEDROCK
        assert (
            point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
            == TEST_MODEL
        )


def test_converse(span_exporter, metric_reader, instrument):
    client = _make_client()
    stubber = Stubber(client)
    stubber.add_response(
        "converse",
        _converse_response(),
        {"modelId": TEST_MODEL, "messages": CONVERSE_MESSAGES},
    )

    with stubber:
        response = client.converse(
            modelId=TEST_MODEL, messages=CONVERSE_MESSAGES
        )

    assert response["stopReason"] == "end_turn"

    span = _get_span(span_exporter)
    _assert_common_request_attributes(
        span, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )

    # response model mirrors the request model for converse
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] == TEST_MODEL

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (list, tuple))
    assert list(finish_reasons) == ["end_turn"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert input_tokens == 10
    assert output_tokens == 5
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)

    _assert_token_usage_metric(metric_reader)

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None


def test_converse_request_parameters(span_exporter, instrument):
    client = _make_client()
    stubber = Stubber(client)
    expected_params = {
        "modelId": TEST_MODEL,
        "messages": CONVERSE_MESSAGES,
        "inferenceConfig": {
            "maxTokens": 128,
            "temperature": 0.5,
            "topP": 0.9,
            "stopSequences": ["STOP"],
        },
    }
    stubber.add_response("converse", _converse_response(), expected_params)

    with stubber:
        client.converse(**expected_params)

    span = _get_span(span_exporter)
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 128
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS], int
    )
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.5
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE], float
    )
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    stop_sequences = span.attributes[
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES
    ]
    assert list(stop_sequences) == ["STOP"]


def test_converse_with_content(span_exporter, instrument_with_content):
    client = _make_client()
    stubber = Stubber(client)
    stubber.add_response(
        "converse",
        _converse_response(),
        {"modelId": TEST_MODEL, "messages": CONVERSE_MESSAGES},
    )

    with stubber:
        client.converse(modelId=TEST_MODEL, messages=CONVERSE_MESSAGES)

    span = _get_span(span_exporter)
    _assert_common_request_attributes(
        span, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )

    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "hello"

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["finish_reason"] == "end_turn"
    assert output_messages[0]["parts"][0]["content"] == "This is a test"


def test_converse_error(span_exporter, metric_reader, instrument):
    client = _make_client()
    stubber = Stubber(client)
    stubber.add_client_error(
        "converse",
        service_error_code="ValidationException",
        service_message="bad request",
        http_status_code=400,
    )

    with stubber:
        with pytest.raises(ClientError) as exc_info:
            client.converse(modelId=TEST_MODEL, messages=CONVERSE_MESSAGES)

    span = _get_span(span_exporter)
    _assert_common_request_attributes(
        span, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == type(exc_info.value).__qualname__

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    error_points = [
        point
        for point in duration_metric.data.data_points
        if ErrorAttributes.ERROR_TYPE in point.attributes
    ]
    assert error_points
    assert error_points[0].attributes[ErrorAttributes.ERROR_TYPE] == error_type


def test_invoke_model_anthropic(span_exporter, metric_reader, instrument):
    client = _make_client()
    stubber = Stubber(client)
    body_bytes = _anthropic_invoke_response_body()
    stubber.add_response(
        "invoke_model",
        {
            "body": StreamingBody(io.BytesIO(body_bytes), len(body_bytes)),
            "contentType": "application/json",
        },
        {"modelId": TEST_MODEL, "body": _anthropic_invoke_body()},
    )

    with stubber:
        response = client.invoke_model(
            modelId=TEST_MODEL, body=_anthropic_invoke_body()
        )
        # the response body must still be readable by the caller
        parsed = json.loads(response["body"].read())

    assert parsed["stop_reason"] == "end_turn"

    span = _get_span(span_exporter)
    _assert_common_request_attributes(
        span, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["end_turn"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert input_tokens == 7
    assert output_tokens == 3
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)

    _assert_token_usage_metric(metric_reader)


def test_invoke_model_with_content(span_exporter, instrument_with_content):
    client = _make_client()
    stubber = Stubber(client)
    body_bytes = _anthropic_invoke_response_body()
    stubber.add_response(
        "invoke_model",
        {
            "body": StreamingBody(io.BytesIO(body_bytes), len(body_bytes)),
            "contentType": "application/json",
        },
        {"modelId": TEST_MODEL, "body": _anthropic_invoke_body()},
    )

    with stubber:
        client.invoke_model(modelId=TEST_MODEL, body=_anthropic_invoke_body())

    span = _get_span(span_exporter)
    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "hello"

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["content"] == "This is a test"


def test_invoke_model_unrecognized_body(span_exporter, instrument):
    """A non-Anthropic body still emits a span with model + operation, but no
    token/finish attributes, and never raises."""
    client = _make_client()
    stubber = Stubber(client)
    # Titan-style response body, not the Anthropic shape.
    titan_body = json.dumps(
        {"results": [{"outputText": "hi", "completionReason": "FINISH"}]}
    ).encode("utf-8")
    request_body = json.dumps({"inputText": "hello"})
    stubber.add_response(
        "invoke_model",
        {
            "body": StreamingBody(io.BytesIO(titan_body), len(titan_body)),
            "contentType": "application/json",
        },
        {"modelId": "amazon.titan-text-express-v1", "body": request_body},
    )

    with stubber:
        response = client.invoke_model(
            modelId="amazon.titan-text-express-v1", body=request_body
        )
        assert json.loads(response["body"].read())["results"]

    span = _get_span(span_exporter)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == AWS_BEDROCK
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == "amazon.titan-text-express-v1"
    )
    # no token usage parsed for an unknown body shape
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
    # a successful response with no stop_reason must not report an "error"
    # finish reason
    assert (
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS not in span.attributes
    )


def test_invoke_model_error(span_exporter, instrument):
    client = _make_client()
    stubber = Stubber(client)
    stubber.add_client_error(
        "invoke_model",
        service_error_code="ThrottlingException",
        service_message="slow down",
        http_status_code=429,
    )

    with stubber:
        with pytest.raises(ClientError) as exc_info:
            client.invoke_model(
                modelId=TEST_MODEL, body=_anthropic_invoke_body()
            )

    span = _get_span(span_exporter)
    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == type(exc_info.value).__qualname__


def test_non_bedrock_client_not_wrapped(span_exporter, instrument):
    """A non bedrock-runtime client must not be instrumented."""
    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="x",
        aws_secret_access_key="x",
    )
    stubber = Stubber(s3)
    stubber.add_response("list_buckets", {"Buckets": []}, {})
    with stubber:
        s3.list_buckets()

    assert span_exporter.get_finished_spans() == ()
