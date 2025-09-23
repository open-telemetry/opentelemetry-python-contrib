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

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from opentelemetry import trace
from opentelemetry._logs import Logger
from opentelemetry.metrics import Histogram
from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.types import AttributeValue

from ..types import InputMessage, LLMInvocation, OutputMessage, Text


@dataclass
class _SpanState:
    span: trace.Span
    context: trace.Context
    start_time: float
    request_model: Optional[str] = None
    system: Optional[str] = None
    children: List[UUID] = field(default_factory=list)


def _message_to_log_record(
    message: InputMessage,
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> Optional[SDKLogRecord]:
    """Build an SDK LogRecord for an input message.

    Returns an SDK-level LogRecord configured with:
    - body: structured payload for the message (when capture_content is True)
    - attributes: includes semconv fields and attributes["event.name"]
    - event_name: mirrors the event name for SDK consumers
    """
    body = asdict(message)
    if not capture_content and body and body.get("parts"):
        for part in body.get("parts", []):
            if part.get("content"):
                part["content"] = ""

    attributes: Dict[str, Any] = {
        "gen_ai.framework": framework,
        "gen_ai.provider.name": provider_name,
        "event.name": "gen_ai.client.inference.operation.details",
    }

    if capture_content:
        attributes["gen_ai.input.messages"] = body

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
    """Build an SDK LogRecord for a chat generation (choice) item.

    Sets both the SDK event_name and attributes["event.name"] to "gen_ai.choice",
    and includes structured fields in body (index, finish_reason, message).
    """
    if not chat_generation:
        return None
    attributes = {
        "gen_ai.framework": framework,
        "gen_ai.provider.name": provider_name,
        "event.name": "gen_ai.choice",
    }

    content: Optional[str] = None
    for part in chat_generation.parts:
        if isinstance(part, Text):
            content = part.content
            break
    message = {
        "type": chat_generation.role,
    }
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
        attributes["gen_ai.framework"] = framework
    if system:
        attributes["gen_ai.provider.name"] = system
    if operation_name:
        attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
    if request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
    if response_model:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model
    return attributes


def _set_initial_span_attributes(
    span: trace.Span,
    request_model: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> None:
    span.set_attribute(
        GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.CHAT.value
    )
    if request_model:
        span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)
    if framework is not None:
        span.set_attribute("gen_ai.framework", framework)
    if system is not None:
        span.set_attribute(GenAI.GEN_AI_SYSTEM, system)
        span.set_attribute("gen_ai.provider.name", system)


def _set_response_and_usage_attributes(
    span: trace.Span,
    response_model: Optional[str],
    response_id: Optional[str],
    prompt_tokens: Optional[AttributeValue],
    completion_tokens: Optional[AttributeValue],
) -> None:
    if response_model is not None:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_MODEL, response_model)
    if response_id is not None:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, response_id)
    if isinstance(prompt_tokens, (int, float)):
        span.set_attribute(GenAI.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens)
    if isinstance(completion_tokens, (int, float)):
        span.set_attribute(GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens)


def _emit_chat_generation_logs(
    logger: Optional[Logger],
    generations: List[OutputMessage],
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> List[str]:
    finish_reasons: List[str] = []
    for index, chat_generation in enumerate(generations):
        log = _chat_generation_to_log_record(
            chat_generation,
            index,
            provider_name,
            framework,
            capture_content=capture_content,
        )
        if log and logger:
            logger.emit(log)
        finish_reasons.append(chat_generation.finish_reason)
    return finish_reasons


def _collect_finish_reasons(generations: List[OutputMessage]) -> List[str]:
    finish_reasons: List[str] = []
    for gen in generations:
        finish_reasons.append(gen.finish_reason)
    return finish_reasons


def _maybe_set_input_messages(
    span: trace.Span, messages: List[InputMessage], capture: bool
) -> None:
    if not capture:
        return
    message_parts: List[Dict[str, Any]] = [
        asdict(message) for message in messages
    ]
    if message_parts:
        span.set_attribute("gen_ai.input.messages", json.dumps(message_parts))


def _set_chat_generation_attrs(
    span: trace.Span, generations: List[OutputMessage]
) -> None:
    for index, chat_generation in enumerate(generations):
        content: Optional[str] = None
        for part in chat_generation.parts:
            if isinstance(part, Text):
                content = part.content
                break
        span.set_attribute(f"gen_ai.completion.{index}.content", content or "")
        span.set_attribute(
            f"gen_ai.completion.{index}.role", chat_generation.role
        )


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
