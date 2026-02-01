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

"""Patching functions for Anthropic instrumentation."""

from typing import TYPE_CHECKING, Any, Callable, Coroutine, Union

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation

from .utils import (
    AsyncMessageStreamManagerWrapper,
    AsyncStreamWrapper,
    MessageWrapper,
    extract_params,
    get_llm_request_attributes,
)

if TYPE_CHECKING:
    from anthropic._streaming import AsyncStream
    from anthropic.lib.streaming import AsyncMessageStreamManager
    from anthropic.resources.messages import AsyncMessages, Messages
    from anthropic.types import Message, RawMessageStreamEvent


def messages_create(
    handler: TelemetryHandler,
) -> Callable[..., "Message"]:
    """Wrap the `create` method of the `Messages` class to trace it."""

    def traced_method(
        wrapped: Callable[..., "Message"],
        instance: "Messages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> "Message":
        params = extract_params(*args, **kwargs)
        attributes = get_llm_request_attributes(params, instance)
        request_model = str(
            attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or params.model
            or "unknown"
        )

        invocation = LLMInvocation(
            request_model=request_model,
            provider="anthropic",
            attributes=attributes,
        )

        with handler.llm(invocation) as invocation:
            result = wrapped(*args, **kwargs)

            if result.model:
                invocation.response_model_name = result.model

            if result.id:
                invocation.response_id = result.id

            if result.stop_reason:
                invocation.finish_reasons = [result.stop_reason]

            if result.usage:
                invocation.input_tokens = result.usage.input_tokens
                invocation.output_tokens = result.usage.output_tokens

            return result

    return traced_method


def async_messages_stream(
    handler: TelemetryHandler,
) -> Callable[..., "AsyncMessageStreamManager"]:
    """Wrap the `stream` method of the `AsyncMessages` class to trace it."""

    def traced_method(
        wrapped: Callable[..., "AsyncMessageStreamManager"],
        instance: "AsyncMessages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> AsyncMessageStreamManagerWrapper:
        params = extract_params(*args, **kwargs)
        attributes = get_llm_request_attributes(params, instance)  # type: ignore[arg-type]
        request_model = str(
            attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or params.model
            or "unknown"
        )

        invocation = LLMInvocation(
            request_model=request_model,
            provider="anthropic",
            attributes=attributes,
        )

        # Start the span before calling the wrapped method
        handler.start_llm(invocation)
        try:
            result = wrapped(*args, **kwargs)
            # Return wrapped AsyncMessageStreamManager
            return AsyncMessageStreamManagerWrapper(
                result, handler, invocation
            )
        except Exception as exc:
            handler.fail_llm(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    return traced_method  # type: ignore[return-value]


def async_messages_create(
    handler: TelemetryHandler,
) -> Callable[
    ...,
    Coroutine[
        Any, Any, Union["Message", "AsyncStream[RawMessageStreamEvent]"]
    ],
]:
    """Wrap the `create` method of the `AsyncMessages` class to trace it."""

    async def traced_method(
        wrapped: Callable[
            ...,
            Coroutine[
                Any,
                Any,
                Union["Message", "AsyncStream[RawMessageStreamEvent]"],
            ],
        ],
        instance: "AsyncMessages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Union["Message", AsyncStreamWrapper]:
        params = extract_params(*args, **kwargs)
        attributes = get_llm_request_attributes(params, instance)  # type: ignore[arg-type]
        request_model = str(
            attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or params.model
            or "unknown"
        )

        invocation = LLMInvocation(
            request_model=request_model,
            provider="anthropic",
            attributes=attributes,
        )

        is_streaming = kwargs.get("stream", False)

        # Use manual lifecycle management for both streaming and non-streaming
        handler.start_llm(invocation)
        try:
            result = await wrapped(*args, **kwargs)
            if is_streaming:
                return AsyncStreamWrapper(result, handler, invocation)  # type: ignore[arg-type]
            wrapper = MessageWrapper(result, handler, invocation)  # type: ignore[arg-type]
            return wrapper.message
        except Exception as exc:
            handler.fail_llm(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    return traced_method  # type: ignore[return-value]
