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

"""Utility functions for ClickHouse GenAI exporter."""

import json
from datetime import datetime
from typing import Any

from opentelemetry.trace import format_span_id, format_trace_id


def ns_to_datetime(nanoseconds: int) -> datetime:
    """Convert nanoseconds timestamp to datetime.

    Args:
        nanoseconds: Timestamp in nanoseconds since epoch.

    Returns:
        datetime object.
    """
    if nanoseconds <= 0:
        return datetime.fromtimestamp(0)
    return datetime.fromtimestamp(nanoseconds / 1e9)


def format_trace_id_fixed(trace_id: int) -> str:
    """Format trace ID as 32-character hex string (FixedString(32)).

    Args:
        trace_id: 128-bit trace ID as integer.

    Returns:
        32-character hex string.
    """
    if trace_id == 0:
        return "0" * 32
    return format_trace_id(trace_id)


def format_span_id_fixed(span_id: int) -> str:
    """Format span ID as 16-character hex string (FixedString(16)).

    Args:
        span_id: 64-bit span ID as integer.

    Returns:
        16-character hex string.
    """
    if span_id == 0:
        return "0" * 16
    return format_span_id(span_id)


def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """Safely serialize object to JSON string.

    Args:
        obj: Object to serialize.
        default: Default value if serialization fails.

    Returns:
        JSON string.
    """
    if obj is None:
        return default
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return default


def extract_genai_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Extract GenAI-specific attributes into dedicated fields.

    This function pops GenAI attributes from the input dict and returns
    them in a structured format suitable for ClickHouse columns.

    Args:
        attrs: Mutable dictionary of span attributes.

    Returns:
        Dictionary with extracted GenAI fields.
    """
    extracted = {
        # Core GenAI attributes
        "GenAiOperationName": attrs.pop("gen_ai.operation.name", ""),
        "GenAiSystem": attrs.pop("gen_ai.system", ""),
        "GenAiRequestModel": attrs.pop("gen_ai.request.model", ""),
        "GenAiResponseModel": attrs.pop("gen_ai.response.model", ""),
        "GenAiResponseId": attrs.pop("gen_ai.response.id", ""),
        # Token usage
        "InputTokens": attrs.pop("gen_ai.usage.input_tokens", 0) or 0,
        "OutputTokens": attrs.pop("gen_ai.usage.output_tokens", 0) or 0,
        "TotalTokens": attrs.pop("llm.usage.total_tokens", 0) or 0,
        "CachedInputTokens": attrs.pop(
            "gen_ai.usage.input_tokens_details.cached", 0
        )
        or 0,
        "ReasoningTokens": attrs.pop(
            "gen_ai.usage.output_tokens_details.reasoning", 0
        )
        or 0,
        "EmbeddingDimensions": attrs.pop(
            "gen_ai.embeddings.dimension.count", 0
        )
        or 0,
        # Request parameters
        "Temperature": attrs.pop("gen_ai.request.temperature", 0) or 0,
        "TopP": attrs.pop("gen_ai.request.top_p", 0) or 0,
        "MaxTokens": attrs.pop("gen_ai.request.max_tokens", 0) or 0,
        "FrequencyPenalty": attrs.pop("gen_ai.request.frequency_penalty", 0)
        or 0,
        "PresencePenalty": attrs.pop("gen_ai.request.presence_penalty", 0)
        or 0,
        "Seed": attrs.pop("gen_ai.request.seed", 0) or 0,
        "ChoiceCount": attrs.pop("gen_ai.request.choice_count", 1) or 1,
        "IsStreaming": 1
        if attrs.pop("gen_ai.request.streaming", False)
        else 0,
        "StopSequences": attrs.pop("gen_ai.request.stop_sequences", []) or [],
        "ReasoningEffort": attrs.pop(
            "gen_ai.openai.request.reasoning_effort", ""
        )
        or "",
        # Response info
        "FinishReasons": attrs.pop("gen_ai.response.finish_reasons", []) or [],
        "ResponseFormatType": attrs.pop(
            "gen_ai.openai.request.response_format", ""
        )
        or "",
        "ServiceTier": attrs.pop("gen_ai.openai.response.service_tier", "")
        or "",
        "SystemFingerprint": attrs.pop(
            "gen_ai.openai.response.system_fingerprint", ""
        )
        or "",
        # Server info
        "ServerAddress": attrs.pop("server.address", "") or "",
        "ServerPort": attrs.pop("server.port", 0) or 0,
        "ApiBaseUrl": attrs.pop("gen_ai.openai.api_base", "") or "",
        "ApiVersion": attrs.pop("gen_ai.openai.api_version", "") or "",
        # Tool calling
        "AvailableTools": attrs.pop("gen_ai.request.available_tools", [])
        or [],
        # Error info
        "ErrorType": attrs.pop("error.type", "") or "",
        # User context
        "UserId": attrs.pop("gen_ai.openai.request.user", "") or "",
        # Content
        "RequestMessages": attrs.pop("gen_ai.request.messages", "") or "",
        "ResponseContent": attrs.pop("gen_ai.response.content", "") or "",
        "RequestPrompt": attrs.pop("gen_ai.request.prompt", "") or "",
        "RequestInput": attrs.pop("gen_ai.request.input", "") or "",
        "StructuredOutputSchema": attrs.pop(
            "gen_ai.request.response_format.schema", ""
        )
        or "",
    }

    # Calculate derived fields
    extracted["HasToolCalls"] = (
        1
        if extracted["AvailableTools"]
        or "tool_calls" in str(extracted.get("FinishReasons", []))
        else 0
    )
    extracted["ToolCallCount"] = len(extracted["AvailableTools"])
    extracted["HasError"] = 1 if extracted["ErrorType"] else 0

    return extracted


def extract_resource_attributes(
    resource_attrs: dict[str, Any],
) -> dict[str, Any]:
    """Extract resource attributes into dedicated fields.

    Args:
        resource_attrs: Dictionary of resource attributes.

    Returns:
        Dictionary with extracted resource fields.
    """
    return {
        "ServiceName": resource_attrs.get("service.name", "unknown"),
        "ServiceVersion": resource_attrs.get("service.version", ""),
        "ServiceNamespace": resource_attrs.get("service.namespace", ""),
        "DeploymentEnvironment": resource_attrs.get(
            "deployment.environment", ""
        ),
        "HostName": resource_attrs.get("host.name", ""),
        "ProcessPid": resource_attrs.get("process.pid", 0) or 0,
        "TelemetrySdkName": resource_attrs.get("telemetry.sdk.name", ""),
        "TelemetrySdkVersion": resource_attrs.get("telemetry.sdk.version", ""),
    }


def extract_metric_genai_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Extract GenAI-specific attributes from metric data points.

    Args:
        attrs: Mutable dictionary of metric attributes.

    Returns:
        Dictionary with extracted GenAI metric fields.
    """
    return {
        "GenAiOperationName": attrs.pop("gen_ai.operation.name", "") or "",
        "GenAiSystem": attrs.pop("gen_ai.system", "") or "",
        "GenAiRequestModel": attrs.pop("gen_ai.request.model", "") or "",
        "GenAiResponseModel": attrs.pop("gen_ai.response.model", "") or "",
        "GenAiTokenType": attrs.pop("gen_ai.token.type", "") or "",
        "ServerAddress": attrs.pop("server.address", "") or "",
        "ServerPort": attrs.pop("server.port", 0) or 0,
        "ErrorType": attrs.pop("error.type", "") or "",
        "ServiceTier": attrs.pop("gen_ai.openai.response.service_tier", "")
        or "",
    }


def extract_log_genai_attributes(
    attrs: dict[str, Any], body: Any
) -> dict[str, Any]:
    """Extract GenAI-specific attributes from log records.

    Args:
        attrs: Mutable dictionary of log attributes.
        body: Log record body.

    Returns:
        Dictionary with extracted GenAI log fields.
    """
    extracted = {
        "GenAiSystem": attrs.pop("gen_ai.system", "") or "",
        "EventName": attrs.pop("event.name", "") or "",
    }

    # Parse body for GenAI log events
    if isinstance(body, dict):
        # For gen_ai.{role}.message events
        extracted["MessageRole"] = body.get("role", "")
        extracted["MessageContent"] = body.get("content", "")
        extracted["ToolCallId"] = body.get("id", "") or body.get(
            "tool_call_id", ""
        )

        # For gen_ai.choice events
        extracted["ChoiceIndex"] = body.get("index", 0)
        extracted["FinishReason"] = body.get("finish_reason", "")

        message = body.get("message", {})
        if message:
            extracted["ChoiceMessageRole"] = message.get("role", "")
            extracted["ChoiceMessageContent"] = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                extracted["ToolCallsJson"] = safe_json_dumps(tool_calls, "[]")
                extracted["HasToolCalls"] = 1
            else:
                extracted["ToolCallsJson"] = "[]"
                extracted["HasToolCalls"] = 0
        else:
            extracted["ChoiceMessageRole"] = ""
            extracted["ChoiceMessageContent"] = ""
            extracted["ToolCallsJson"] = "[]"
            extracted["HasToolCalls"] = 0
    else:
        # Set defaults for non-dict bodies
        extracted["MessageRole"] = ""
        extracted["MessageContent"] = ""
        extracted["ToolCallId"] = ""
        extracted["ChoiceIndex"] = 0
        extracted["FinishReason"] = ""
        extracted["ChoiceMessageRole"] = ""
        extracted["ChoiceMessageContent"] = ""
        extracted["ToolCallsJson"] = "[]"
        extracted["HasToolCalls"] = 0

    return extracted
