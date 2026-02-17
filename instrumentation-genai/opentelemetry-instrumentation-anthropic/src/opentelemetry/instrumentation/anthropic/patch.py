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

from typing import TYPE_CHECKING, Any, Callable, Union

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation
from opentelemetry.util.genai.utils import should_capture_content

from .messages_extractors import (
    extract_params,
    get_input_messages,
    get_llm_request_attributes,
    get_system_instruction,
)
from .wrappers import (
    MessageWrapper,
    StreamWrapper,
)

if TYPE_CHECKING:
    from anthropic._streaming import Stream
    from anthropic.resources.messages import Messages
    from anthropic.types import Message, RawMessageStreamEvent


ANTHROPIC = "anthropic"


def messages_create(
    handler: TelemetryHandler,
) -> Callable[..., Union["Message", "Stream[RawMessageStreamEvent]"]]:
    """Wrap the `create` method of the `Messages` class to trace it."""

    def traced_method(
        wrapped: Callable[
            ..., Union["Message", "Stream[RawMessageStreamEvent]"]
        ],
        instance: "Messages",
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Union["Message", StreamWrapper]:
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

        capture_content = should_capture_content()
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

        is_streaming = kwargs.get("stream", False)

        # Use manual lifecycle management for both streaming and non-streaming
        handler.start_llm(invocation)
        try:
            result = wrapped(*args, **kwargs)
            if is_streaming:
                return StreamWrapper(result, handler, invocation)  # type: ignore[arg-type]
            wrapper = MessageWrapper(result)  # type: ignore[arg-type]
            wrapper.extract_into(invocation)
            handler.stop_llm(invocation)
            return wrapper.message
        except Exception as exc:
            handler.fail_llm(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    return traced_method  # type: ignore[return-value]
