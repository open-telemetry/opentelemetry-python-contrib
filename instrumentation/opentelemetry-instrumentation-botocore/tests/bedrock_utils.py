# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
from typing import Any

from botocore.response import StreamingBody

from opentelemetry.instrumentation.botocore.extensions.bedrock import (
    _GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS,
    _GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS,
)
from opentelemetry.sdk.metrics._internal.point import ResourceMetrics
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    event_attributes as EventAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes.error_attributes import (
    ERROR_TYPE,
)
from opentelemetry.semconv._incubating.metrics.gen_ai_metrics import (
    GEN_AI_CLIENT_OPERATION_DURATION,
    GEN_AI_CLIENT_TOKEN_USAGE,
)


# pylint: disable=too-many-branches, too-many-locals
def assert_completion_attributes_from_streaming_body(
    span: ReadableSpan,
    request_model: str,
    response: StreamingBody | None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    input_tokens = None
    output_tokens = None
    finish_reason = None
    if response is not None:
        original_body = response["body"]
        body_content = original_body.read()
        response = json.loads(body_content.decode("utf-8"))
        assert response

        if "amazon.titan" in request_model:
            input_tokens = response.get("inputTextTokenCount")
            results = response.get("results")
            if results:
                first_result = results[0]
                output_tokens = first_result.get("tokenCount")
                finish_reason = (first_result["completionReason"],)
        elif "amazon.nova" in request_model:
            if usage := response.get("usage"):
                input_tokens = usage["inputTokens"]
                output_tokens = usage["outputTokens"]
            else:
                input_tokens, output_tokens = None, None

            if "stopReason" in response:
                finish_reason = (response["stopReason"],)
            else:
                finish_reason = None
        elif "anthropic.claude" in request_model:
            if usage := response.get("usage"):
                input_tokens = usage["input_tokens"]
                output_tokens = usage["output_tokens"]
            else:
                input_tokens, output_tokens = None, None

            if "stop_reason" in response:
                finish_reason = (response["stop_reason"],)
            else:
                finish_reason = None

    return assert_all_attributes(
        span,
        request_model,
        input_tokens,
        output_tokens,
        finish_reason,
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences)
        if request_stop_sequences is not None
        else request_stop_sequences,
    )


def assert_converse_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: dict[str, Any] | None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    if usage := (response and response.get("usage")):
        input_tokens = usage["inputTokens"]
        output_tokens = usage["outputTokens"]
    else:
        input_tokens, output_tokens = None, None

    if response and "stopReason" in response:
        finish_reason = (response["stopReason"],)
    else:
        finish_reason = None

    return assert_all_attributes(
        span,
        request_model,
        input_tokens,
        output_tokens,
        finish_reason,
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences)
        if request_stop_sequences is not None
        else request_stop_sequences,
    )


def assert_stream_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finish_reason: tuple[str] | None = None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    return assert_all_attributes(
        span,
        request_model,
        input_tokens,
        output_tokens,
        finish_reason,
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences)
        if request_stop_sequences is not None
        else request_stop_sequences,
    )


def assert_equal_or_not_present(value, attribute_name, span):
    if value is not None:
        assert attribute_name in span.attributes
        assert value == span.attributes[attribute_name], span.attributes[
            attribute_name
        ]
    else:
        assert attribute_name not in span.attributes, attribute_name


def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finish_reason: tuple[str] | None = None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: tuple[str] | None = None,
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    assert (
        GenAIAttributes.GenAiSystemValues.AWS_BEDROCK.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )

    assert_equal_or_not_present(
        input_tokens, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, span
    )
    assert_equal_or_not_present(
        output_tokens, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, span
    )
    assert_equal_or_not_present(
        finish_reason, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, span
    )
    assert_equal_or_not_present(
        request_top_p, GenAIAttributes.GEN_AI_REQUEST_TOP_P, span
    )
    assert_equal_or_not_present(
        request_temperature, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, span
    )
    assert_equal_or_not_present(
        request_max_tokens, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, span
    )
    assert_equal_or_not_present(
        request_stop_sequences,
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES,
        span,
    )


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


def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert (
        log.log_record.attributes[EventAttributes.EVENT_NAME] == event_name
    ), log.log_record.attributes[EventAttributes.EVENT_NAME]
    assert (
        log.log_record.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.AWS_BEDROCK.value
    )

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == remove_none_values(
            expected_content
        ), dict(log.log_record.body)
    assert_log_parent(log, parent_span)


def assert_invoke_agent_attributes(span, agent_id, agent_alias_id, session_id, has_tool_call=False, is_result_call=False):
    # Check system and operation name
    assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == GenAIAttributes.GenAiSystemValues.AWS_BEDROCK.value
    assert span.attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME) == "invoke_agent"

    # Check agent attributes
    assert span.attributes.get(GenAIAttributes.GEN_AI_AGENT_ID) == agent_id
    assert span.attributes.get(GenAIAttributes.GEN_AI_AGENT_NAME) == agent_alias_id

    # If tool call exists, check tool attributes
    if has_tool_call:
        assert GenAIAttributes.GEN_AI_TOOL_CALL_ID in span.attributes
        assert GenAIAttributes.GEN_AI_TOOL_NAME in span.attributes
        assert GenAIAttributes.GEN_AI_TOOL_TYPE in span.attributes
        allowed_tool_types = {"extension", "function", "datastore"}
        assert span.attributes.get(GenAIAttributes.GEN_AI_TOOL_TYPE) in allowed_tool_types, \
            f"Unexpected tool type in span: {span.attributes.get(GenAIAttributes.GEN_AI_TOOL_TYPE)}"
    elif is_result_call:
        assert GenAIAttributes.GEN_AI_TOOL_CALL_ID not in span.attributes
        assert GenAIAttributes.GEN_AI_TOOL_NAME not in span.attributes
        assert GenAIAttributes.GEN_AI_TOOL_TYPE not in span.attributes


def assert_all_metric_attributes(
    data_point, operation_name: str, model: str, error_type: str | None = None
):
    assert GenAIAttributes.GEN_AI_OPERATION_NAME in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == operation_name
    )
    assert GenAIAttributes.GEN_AI_SYSTEM in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.AWS_BEDROCK.value
    )
    if model is not None:
        assert GenAIAttributes.GEN_AI_REQUEST_MODEL in data_point.attributes
        assert data_point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model

    if error_type is not None:
        assert ERROR_TYPE in data_point.attributes
        assert data_point.attributes[ERROR_TYPE] == error_type
    else:
        assert ERROR_TYPE not in data_point.attributes


def assert_metrics(
    resource_metrics: ResourceMetrics,
    operation_name: str,
    model: str,
    input_tokens: float | None = None,
    output_tokens: float | None = None,
    error_type: str | None = None,
):
    assert len(resource_metrics) == 1

    metric_data = resource_metrics[0].scope_metrics[0].metrics
    if input_tokens is not None or output_tokens is not None:
        expected_metrics_data_len = 2
    else:
        expected_metrics_data_len = 1
    assert len(metric_data) == expected_metrics_data_len

    duration_metric = next(
        (m for m in metric_data if m.name == GEN_AI_CLIENT_OPERATION_DURATION),
        None,
    )
    assert duration_metric is not None

    duration_point = duration_metric.data.data_points[0]
    assert duration_point.sum > 0
    assert_all_metric_attributes(
        duration_point, operation_name, model, error_type
    )
    assert duration_point.explicit_bounds == tuple(
        _GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS
    )

    if input_tokens is not None:
        token_usage_metric = next(
            (m for m in metric_data if m.name == GEN_AI_CLIENT_TOKEN_USAGE),
            None,
        )
        assert token_usage_metric is not None

        input_token_usage = next(
            (
                d
                for d in token_usage_metric.data.data_points
                if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
                == GenAIAttributes.GenAiTokenTypeValues.INPUT.value
            ),
            None,
        )
        assert input_token_usage is not None
        assert input_token_usage.sum == input_tokens

        assert input_token_usage.explicit_bounds == tuple(
            _GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS
        )
        assert_all_metric_attributes(input_token_usage, operation_name, model)

    if output_tokens is not None:
        token_usage_metric = next(
            (m for m in metric_data if m.name == GEN_AI_CLIENT_TOKEN_USAGE),
            None,
        )
        assert token_usage_metric is not None

        output_token_usage = next(
            (
                d
                for d in token_usage_metric.data.data_points
                if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
                == GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
            ),
            None,
        )
        assert output_token_usage is not None
        assert output_token_usage.sum == output_tokens

        assert output_token_usage.explicit_bounds == tuple(
            _GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS
        )
        assert_all_metric_attributes(output_token_usage, operation_name, model)
