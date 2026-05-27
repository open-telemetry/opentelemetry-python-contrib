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

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Union, cast

from anthropic._streaming import AsyncStream as AnthropicAsyncStream
from anthropic._streaming import Stream as AnthropicStream
from anthropic.types import Message as AnthropicMessage

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation
from opentelemetry.util.genai.utils import (
    should_capture_content_on_spans_in_experimental_mode,
)

from .messages_extractors import (
    MessageRequestParams,
    extract_params,
    get_input_messages,
    get_llm_request_attributes,
    get_system_instruction,
)
from .wrappers import (
    AsyncMessagesStreamManagerWrapper,
    AsyncMessagesStreamWrapper,
    MessagesStreamManagerWrapper,
    MessagesStreamWrapper,
    MessageWrapper,
)

if TYPE_CHECKING:
    from anthropic.lib.streaming._messages import (  # pylint: disable=no-name-in-module
        AsyncMessageStreamManager,
        MessageStreamManager,
    )
    from anthropic.resources.messages import AsyncMessages, Messages
    from anthropic.types import RawMessageStreamEvent


_logger = logging.getLogger(__name__)
ANTHROPIC = "anthropic"


def _build_invocation(
    params: MessageRequestParams,
    instance: "Messages | AsyncMessages",
    capture_content: bool,
) -> LLMInvocation:
    attributes = get_llm_request_attributes(params, instance)  # type: ignore[arg-type]
    request_model_attribute = attributes.get(
        GenAIAttributes.GEN_AI_REQUEST_MODEL
    )
    request_model = (
        request_model_attribute
        if isinstance(request_model_attribute, str)
        else params.model
    )

    return LLMInvocation(
        request_model=request_model,
        provider=ANTHROPIC,
        input_messages=get_input_messages(params.messages)
        if capture_content
        else [],
        system_instruction=get_system_instruction(params.system)
        if capture_content
        else [],
        attributes=attributes,
    )


def _fail_invocation(
    handler: TelemetryHandler,
    invocation: LLMInvocation,
    exc: Exception,
) -> None:
    handler.fail_llm(invocation, Error(message=str(exc), type=type(exc)))


def messages_create(
    handler: TelemetryHandler,
) -> Callable[
    ...,
    Union[
        "AnthropicMessage",
        "AnthropicStream[RawMessageStreamEvent]",
        MessagesStreamWrapper[None],
    ],
]:
    """Wrap the sync ``Messages.create`` method to trace it."""
    capture_content = should_capture_content_on_spans_in_experimental_mode()

    def traced_method(
        wrapped: Callable[
            ...,
            Union[
                "AnthropicMessage",
                "AnthropicStream[RawMessageStreamEvent]",
            ],
        ],
        instance: "Messages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Union[
        "AnthropicMessage",
        "AnthropicStream[RawMessageStreamEvent]",
        MessagesStreamWrapper[None],
    ]:
        params = extract_params(*args, **kwargs)
        invocation = _build_invocation(params, instance, capture_content)

        handler.start_llm(invocation)
        try:
            result = wrapped(*args, **kwargs)
            if isinstance(result, AnthropicStream):
                return MessagesStreamWrapper(
                    result, handler, invocation, capture_content
                )

            wrapper = MessageWrapper(result, capture_content)
            wrapper.extract_into(invocation)
            handler.stop_llm(invocation)
            return wrapper.message
        except Exception as exc:
            _fail_invocation(handler, invocation, exc)
            raise

    return cast(
        'Callable[..., Union["AnthropicMessage", "AnthropicStream[RawMessageStreamEvent]", MessagesStreamWrapper[None]]]',
        traced_method,
    )


def async_messages_create(
    handler: TelemetryHandler,
) -> Callable[
    ...,
    Awaitable[
        Union[
            "AnthropicMessage",
            "AnthropicAsyncStream[RawMessageStreamEvent]",
            AsyncMessagesStreamWrapper[None],
        ]
    ],
]:
    """Wrap the async ``AsyncMessages.create`` method to trace it."""
    capture_content = should_capture_content_on_spans_in_experimental_mode()

    async def traced_method(
        wrapped: Callable[
            ...,
            Awaitable[
                Union[
                    "AnthropicMessage",
                    "AnthropicAsyncStream[RawMessageStreamEvent]",
                ]
            ],
        ],
        instance: "AsyncMessages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Union[
        "AnthropicMessage",
        "AnthropicAsyncStream[RawMessageStreamEvent]",
        AsyncMessagesStreamWrapper[None],
    ]:
        params = extract_params(*args, **kwargs)
        invocation = _build_invocation(params, instance, capture_content)

        handler.start_llm(invocation)
        try:
            result = await wrapped(*args, **kwargs)
            if isinstance(result, AnthropicAsyncStream):
                return AsyncMessagesStreamWrapper(
                    result, handler, invocation, capture_content
                )

            wrapper = MessageWrapper(result, capture_content)
            wrapper.extract_into(invocation)
            handler.stop_llm(invocation)
            return wrapper.message
        except Exception as exc:
            _fail_invocation(handler, invocation, exc)
            raise

    return cast(
        'Callable[..., Awaitable[Union["AnthropicMessage", "AnthropicAsyncStream[RawMessageStreamEvent]", AsyncMessagesStreamWrapper[None]]]]',
        traced_method,
    )


def messages_stream(
    handler: TelemetryHandler,
) -> Callable[..., "MessagesStreamManagerWrapper[Any]"]:
    """Wrap the sync ``Messages.stream`` method to trace message streams."""
    capture_content = should_capture_content_on_spans_in_experimental_mode()

    def traced_method(
        wrapped: Callable[..., "MessageStreamManager[Any]"],
        instance: "Messages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> "MessagesStreamManagerWrapper[Any]":
        params = extract_params(*args, **kwargs)
        invocation = _build_invocation(params, instance, capture_content)

        handler.start_llm(invocation)
        try:
            manager = wrapped(*args, **kwargs)
            return MessagesStreamManagerWrapper(
                manager, handler, invocation, capture_content
            )
        except Exception as exc:
            _fail_invocation(handler, invocation, exc)
            raise

    return traced_method


def async_messages_stream(
    handler: TelemetryHandler,
) -> Callable[..., "AsyncMessagesStreamManagerWrapper[Any]"]:
    """Wrap the async ``AsyncMessages.stream`` method to trace message streams."""
    capture_content = should_capture_content_on_spans_in_experimental_mode()

    def traced_method(
        wrapped: Callable[..., "AsyncMessageStreamManager[Any]"],
        instance: "AsyncMessages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> "AsyncMessagesStreamManagerWrapper[Any]":
        params = extract_params(*args, **kwargs)
        invocation = _build_invocation(params, instance, capture_content)

        handler.start_llm(invocation)
        try:
            manager = wrapped(*args, **kwargs)
            return AsyncMessagesStreamManagerWrapper(
                manager, handler, invocation, capture_content
            )
        except Exception as exc:
            _fail_invocation(handler, invocation, exc)
            raise

    return traced_method
