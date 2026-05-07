# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Patching functions for Anthropic instrumentation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Union, cast

from anthropic._streaming import Stream as AnthropicStream
from anthropic.types import Message as AnthropicMessage

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    LLMInvocation,  # TODO: migrate to InferenceInvocation
)
from opentelemetry.util.genai.utils import (
    should_capture_content_on_spans_in_experimental_mode,
)

from .messages_extractors import (
    extract_params,
    get_input_messages,
    get_llm_request_attributes,
    get_system_instruction,
)
from .wrappers import (
    MessagesStreamWrapper,
    MessageWrapper,
)

if TYPE_CHECKING:
    from anthropic.resources.messages import Messages
    from anthropic.types import RawMessageStreamEvent


_logger = logging.getLogger(__name__)
ANTHROPIC = "anthropic"


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
    """Wrap the `create` method of the `Messages` class to trace it."""
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
        attributes = get_llm_request_attributes(params, instance)
        request_model_attribute = attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        )
        request_model = (
            request_model_attribute
            if isinstance(request_model_attribute, str)
            else params.model
        )

        invocation = LLMInvocation(
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

        # Use manual lifecycle management for both streaming and non-streaming
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
            handler.fail_llm(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    return cast(
        'Callable[..., Union["AnthropicMessage", "AnthropicStream[RawMessageStreamEvent]", MessagesStreamWrapper[None]]]',
        traced_method,
    )
