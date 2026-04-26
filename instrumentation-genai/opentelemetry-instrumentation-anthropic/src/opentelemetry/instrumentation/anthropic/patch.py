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
from typing import TYPE_CHECKING, Any, Callable, Union, cast

from anthropic._streaming import Stream as AnthropicStream
from anthropic.types import Message as AnthropicMessage

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
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
    MessagesStreamManagerWrapper,
    MessagesStreamWrapper,
    MessageWrapper,
)

if TYPE_CHECKING:
    from anthropic.lib.streaming._messages import (  # pylint: disable=no-name-in-module
        MessageStreamManager,
    )
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
        invocation, capture_content = _create_invocation(
            handler, instance, args, kwargs
        )
        try:
            result = wrapped(*args, **kwargs)
            if isinstance(result, AnthropicStream):
                return MessagesStreamWrapper(
                    result, invocation, capture_content
                )

            wrapper = MessageWrapper(result, capture_content)
            wrapper.extract_into(invocation)
            invocation.stop()
            return wrapper.message
        except Exception as exc:
            invocation.fail(exc)
            raise

    return cast(
        'Callable[..., Union["AnthropicMessage", "AnthropicStream[RawMessageStreamEvent]", MessagesStreamWrapper[None]]]',
        traced_method,
    )


def _create_invocation(
    handler: TelemetryHandler,
    instance: "Messages",
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[InferenceInvocation, bool]:
    capture_content = should_capture_content_on_spans_in_experimental_mode()
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

    invocation = handler.start_inference(
        provider=ANTHROPIC,
        request_model=request_model,
    )
    invocation.input_messages = (
        get_input_messages(params.messages) if capture_content else []
    )
    invocation.system_instruction = (
        get_system_instruction(params.system) if capture_content else []
    )
    invocation.attributes = attributes
    return invocation, capture_content


def messages_stream(
    handler: TelemetryHandler,
) -> Callable[..., MessagesStreamManagerWrapper[Any]]:
    """Wrap the sync `stream` method of the `Messages` class."""

    def traced_method(
        wrapped: Callable[..., "MessageStreamManager[Any]"],
        instance: "Messages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> MessagesStreamManagerWrapper[Any]:
        invocation, capture_content = _create_invocation(
            handler, instance, args, kwargs
        )

        try:
            return MessagesStreamManagerWrapper(
                wrapped(*args, **kwargs), invocation, capture_content
            )
        except Exception as exc:
            invocation.fail(exc)
            raise

    return cast(
        "Callable[..., MessagesStreamManagerWrapper[Any]]", traced_method
    )
