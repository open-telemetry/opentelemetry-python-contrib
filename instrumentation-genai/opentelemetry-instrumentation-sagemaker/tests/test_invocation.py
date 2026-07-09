# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the AWS SageMaker instrumentation.

These tests never touch the network. They use the ``botocore`` ``Stubber`` to
return canned ``invoke_endpoint`` responses (and errors), so the instrumentation
wrapper runs end-to-end against real ``boto3``/``botocore`` client types.

The instrumentor wraps ``invoke_endpoint`` at *client-creation* time, so each
test instruments before creating the ``sagemaker-runtime`` client (the
``instrument`` fixture is a dependency of every test and runs first).

The tests exercise the latest-experimental semantic-convention path
(``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental``), which is what the
``instrument`` fixture enables.
"""

import io

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import StatusCode

ENDPOINT_NAME = "my-endpoint"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
SAGEMAKER = "aws.sagemaker"


def _make_client():
    return boto3.client(
        "sagemaker-runtime",
        region_name="us-east-1",
        aws_access_key_id="x",
        aws_secret_access_key="x",
    )


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


def _assert_common_request_attributes(span):
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str
    )
    # experimental path uses gen_ai.provider.name (not gen_ai.system).
    # aws.sagemaker has no GenAiProviderNameValues member, so it is a literal.
    assert span.attributes[GEN_AI_PROVIDER_NAME] == SAGEMAKER
    assert isinstance(span.attributes[GEN_AI_PROVIDER_NAME], str)
    # gen_ai.request.model carries the SageMaker endpoint name.
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == ENDPOINT_NAME
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str
    )


def test_invoke_endpoint(span_exporter, metric_reader, instrument):
    client = _make_client()
    stubber = Stubber(client)
    stubber.add_response(
        "invoke_endpoint",
        {
            "Body": StreamingBody(io.BytesIO(b"{}"), 2),
            "ContentType": "application/json",
        },
        {"EndpointName": ENDPOINT_NAME, "Body": b"..."},
    )

    with stubber:
        response = client.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            Body=b"...",
        )

    span = _get_span(span_exporter)
    assert span.name == f"chat {ENDPOINT_NAME}"
    _assert_common_request_attributes(span)
    assert span.status.status_code != StatusCode.ERROR

    # The opaque response Body must be intact/unconsumed by the instrumentation.
    assert response["Body"].read() == b"{}"

    # Thin telemetry: no token usage, finish reasons, response model, etc.
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
    assert (
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS not in span.attributes
    )
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL not in span.attributes

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_points = list(duration_metric.data.data_points)
    assert len(duration_points) == 1
    assert duration_points[0].sum >= 0


def test_invoke_endpoint_error(span_exporter, metric_reader, instrument):
    client = _make_client()
    stubber = Stubber(client)
    stubber.add_client_error(
        "invoke_endpoint",
        service_error_code="ValidationError",
        service_message="endpoint not found",
        http_status_code=400,
    )

    with stubber:
        with pytest.raises(Exception) as exc_info:
            client.invoke_endpoint(
                EndpointName=ENDPOINT_NAME,
                Body=b"...",
            )

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)
    assert span.status.status_code == StatusCode.ERROR

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    # The original botocore exception is re-raised unmodified.
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
