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

"""Patching functions for Groq instrumentation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, cast

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)
from opentelemetry.util.genai.utils import (
    should_capture_content_on_spans_in_experimental_mode,
)

if TYPE_CHECKING:
    from groq.resources.chat.completions import AsyncCompletions, Completions

_logger = logging.getLogger(__name__)
GROQ = "groq"


@dataclass
class ChatCompletionParams:
    model: str | None = None
    messages: list[Any] | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: str | list[str] | None = None
    stream: bool | None = None


def extract_params(
    *,
    model: str | None = None,
    messages: list[Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    stop: str | list[str] | None = None,
    stream: bool | None = None,
    **_kwargs: object,
) -> ChatCompletionParams:
    return ChatCompletionParams(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop,
        stream=stream,
    )


def _get_server_address_and_port(
    instance: Any,
    attributes: dict[str, Any],
) -> None:
    try:
        base_url = instance._client.base_url
        host = base_url.host
        if host:
            attributes[ServerAttributes.SERVER_ADDRESS] = host
        port = base_url.port
        if port and port != 443 and port > 0:
            attributes[ServerAttributes.SERVER_PORT] = port
    except AttributeError:
        pass


def get_llm_request_attributes(
    params: ChatCompletionParams,
    instance: Any,
) -> dict[str, Any]:
    stop_sequences: tuple[str, ...] | None = None
    if isinstance(params.stop, str):
        stop_sequences = (params.stop,)
    elif isinstance(params.stop, list):
        stop_sequences = tuple(params.stop)

    attributes: dict[str, Any] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.GROQ.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: params.model,
    }
    if params.max_tokens is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] = (
            params.max_tokens
        )
    if params.temperature is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] = (
            params.temperature
        )
    if params.top_p is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] = params.top_p
    if stop_sequences is not None:
        attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] = (
            stop_sequences
        )

    _get_server_address_and_port(instance, attributes)
    return attributes


def get_input_messages(messages: list[Any] | None) -> list[InputMessage]:
    if not messages:
        return []
    result: list[InputMessage] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
        parts = (
            [Text(content=content)]
            if isinstance(content, str) and content
            else []
        )
        result.append(InputMessage(role=role, parts=parts))
    return result


def _extract_response(
    result: Any,
    invocation: LLMInvocation,
    capture_content: bool,
) -> None:
    if getattr(result, "model", None):
        invocation.response_model_name = result.model
    if getattr(result, "id", None):
        invocation.response_id = result.id

    choices = getattr(result, "choices", None) or []
    finish_reason: str | None = None
    if choices:
        finish_reason = getattr(choices[0], "finish_reason", None)
        if finish_reason:
            invocation.finish_reasons = [finish_reason]

        if capture_content:
            message = getattr(choices[0], "message", None)
            if message:
                content = getattr(message, "content", None)
                role = getattr(message, "role", "assistant") or "assistant"
                if content:
                    invocation.output_messages = [
                        OutputMessage(
                            role=role,
                            parts=[Text(content=content)],
                            finish_reason=finish_reason or "",
                        )
                    ]

    usage = getattr(result, "usage", None)
    if usage:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        if prompt_tokens is not None:
            invocation.input_tokens = prompt_tokens
        if completion_tokens is not None:
            invocation.output_tokens = completion_tokens


def chat_completions_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``Completions.create`` to emit traces and metrics."""
    capture_content = should_capture_content_on_spans_in_experimental_mode()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: "Completions",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        params = extract_params(**kwargs)
        attributes = get_llm_request_attributes(params, instance)
        request_model_attr = attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        )
        request_model = (
            request_model_attr
            if isinstance(request_model_attr, str)
            else params.model
        )

        invocation = LLMInvocation(
            request_model=request_model,
            provider=GROQ,
            input_messages=get_input_messages(params.messages)
            if capture_content
            else [],
            attributes=attributes,
        )

        handler.start_llm(invocation)
        try:
            result = wrapped(*args, **kwargs)
            _extract_response(result, invocation, capture_content)
            handler.stop_llm(invocation)
            return result
        except Exception as exc:
            handler.fail_llm(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    return cast(Callable[..., Any], traced_method)


def async_chat_completions_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``AsyncCompletions.create`` to emit traces and metrics."""
    capture_content = should_capture_content_on_spans_in_experimental_mode()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: "AsyncCompletions",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        params = extract_params(**kwargs)
        attributes = get_llm_request_attributes(params, instance)
        request_model_attr = attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        )
        request_model = (
            request_model_attr
            if isinstance(request_model_attr, str)
            else params.model
        )

        invocation = LLMInvocation(
            request_model=request_model,
            provider=GROQ,
            input_messages=get_input_messages(params.messages)
            if capture_content
            else [],
            attributes=attributes,
        )

        handler.start_llm(invocation)
        try:
            result = await wrapped(*args, **kwargs)
            _extract_response(result, invocation, capture_content)
            handler.stop_llm(invocation)
            return result
        except Exception as exc:
            handler.fail_llm(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    return cast(Callable[..., Any], traced_method)
