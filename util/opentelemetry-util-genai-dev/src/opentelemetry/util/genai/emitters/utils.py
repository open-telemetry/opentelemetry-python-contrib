# Shared utility functions for GenAI emitters (migrated from generators/utils.py)
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry._logs import (
    Logger,  # noqa: F401 (kept for backward compatibility if referenced externally)
)
from opentelemetry.metrics import Histogram
from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.types import AttributeValue

from ..attributes import (
    GEN_AI_FRAMEWORK,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_PROVIDER_NAME,
)
from ..types import InputMessage, LLMInvocation, OutputMessage, Text


def _serialize_messages(messages) -> Optional[str]:
    """Safely JSON serialize a sequence of dataclass messages.

    Returns a JSON string or None on failure.
    """
    try:  # pragma: no cover - defensive
        return json.dumps([asdict(m) for m in messages])
    except Exception:  # pragma: no cover
        return None


def _apply_function_definitions(
    span: trace.Span, request_functions: Optional[List[dict]]
) -> None:
    """Apply request function definition attributes (idempotent).

    Shared between span emitters to avoid duplicated loops.
    """
    if not request_functions:
        return
    for idx, fn in enumerate(request_functions):
        try:
            name = fn.get("name")
            if name:
                span.set_attribute(f"gen_ai.request.function.{idx}.name", name)
            desc = fn.get("description")
            if desc:
                span.set_attribute(
                    f"gen_ai.request.function.{idx}.description", desc
                )
            params = fn.get("parameters")
            if params is not None:
                span.set_attribute(
                    f"gen_ai.request.function.{idx}.parameters", str(params)
                )
        except Exception:  # pragma: no cover - defensive
            pass


def _apply_llm_finish_semconv(
    span: trace.Span, invocation: LLMInvocation
) -> None:
    """Apply finish-time semantic convention attributes for an LLMInvocation.

    Includes response model/id, usage tokens, and function definitions (re-applied).
    """
    try:  # pragma: no cover - defensive
        if invocation.response_model_name:
            span.set_attribute(
                GenAI.GEN_AI_RESPONSE_MODEL, invocation.response_model_name
            )
        if invocation.response_id:
            span.set_attribute(
                GenAI.GEN_AI_RESPONSE_ID, invocation.response_id
            )
        if invocation.input_tokens is not None:
            span.set_attribute(
                GenAI.GEN_AI_USAGE_INPUT_TOKENS, invocation.input_tokens
            )
        if invocation.output_tokens is not None:
            span.set_attribute(
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, invocation.output_tokens
            )
        _apply_function_definitions(span, invocation.request_functions)
    except Exception:  # pragma: no cover
        pass


def _message_to_log_record(
    message: InputMessage,
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> Optional[SDKLogRecord]:
    body = asdict(message)
    if not capture_content and body and body.get("parts"):
        for part in body.get("parts", []):
            if part.get("content"):
                part["content"] = ""

    attributes: Dict[str, Any] = {
        GEN_AI_FRAMEWORK: framework,
        GEN_AI_PROVIDER_NAME: provider_name,
        "event.name": "gen_ai.client.inference.operation.details",
    }

    if capture_content:
        attributes[GEN_AI_INPUT_MESSAGES] = body

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.client.inference.operation.details",
    )


def _chat_generation_to_log_record(
    chat_generation: OutputMessage,
    index: int,
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> Optional[SDKLogRecord]:
    if not chat_generation:
        return None
    attributes = {
        GEN_AI_FRAMEWORK: framework,
        GEN_AI_PROVIDER_NAME: provider_name,
        "event.name": "gen_ai.choice",
    }
    content: Optional[str] = None
    for part in chat_generation.parts:
        if isinstance(part, Text):
            content = part.content
            break
    message = {"type": chat_generation.role}
    if capture_content and content is not None:
        message["content"] = content

    body = {
        "index": index,
        "finish_reason": chat_generation.finish_reason or "error",
        "message": message,
    }
    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.choice",
    )


def _get_metric_attributes(
    request_model: Optional[str],
    response_model: Optional[str],
    operation_name: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> Dict[str, AttributeValue]:
    attributes: Dict[str, AttributeValue] = {}
    if framework is not None:
        attributes[GEN_AI_FRAMEWORK] = framework
    if system:
        # NOTE: The 'system' parameter historically mapped to provider name; keeping for backward compatibility.
        attributes[GEN_AI_PROVIDER_NAME] = system
    if operation_name:
        attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
    if request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
    if response_model:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model
    return attributes


def _record_token_metrics(
    token_histogram: Histogram,
    prompt_tokens: Optional[AttributeValue],
    completion_tokens: Optional[AttributeValue],
    metric_attributes: Dict[str, AttributeValue],
) -> None:
    prompt_attrs: Dict[str, AttributeValue] = {
        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.INPUT.value
    }
    prompt_attrs.update(metric_attributes)
    if isinstance(prompt_tokens, (int, float)):
        token_histogram.record(prompt_tokens, attributes=prompt_attrs)

    completion_attrs: Dict[str, AttributeValue] = {
        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.COMPLETION.value
    }
    completion_attrs.update(metric_attributes)
    if isinstance(completion_tokens, (int, float)):
        token_histogram.record(completion_tokens, attributes=completion_attrs)


def _record_duration(
    duration_histogram: Histogram,
    invocation: LLMInvocation,
    metric_attributes: Dict[str, AttributeValue],
) -> None:
    if invocation.end_time is not None:
        elapsed: float = invocation.end_time - invocation.start_time
        duration_histogram.record(elapsed, attributes=metric_attributes)
