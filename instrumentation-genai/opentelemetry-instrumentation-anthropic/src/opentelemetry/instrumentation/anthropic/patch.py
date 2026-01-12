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

from typing import Any, Callable

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import LLMInvocation

from .utils import (
    get_llm_request_attributes,
    parse_input_messages,
    parse_output_message,
)


def messages_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the `create` method of the `Messages` class to trace it."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        attributes = get_llm_request_attributes(kwargs, instance)
        request_model = str(
            attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or kwargs.get("model")
            or "unknown"
        )

        # Parse input messages
        input_messages = parse_input_messages(kwargs.get("messages", []))

        invocation = LLMInvocation(
            request_model=request_model,
            provider="anthropic",
            attributes=attributes,
            input_messages=input_messages,
        )

        with handler.llm(invocation) as invocation:
            result = wrapped(*args, **kwargs)

            if getattr(result, "model", None):
                invocation.response_model_name = result.model

            if getattr(result, "id", None):
                invocation.response_id = result.id

            if getattr(result, "stop_reason", None):
                invocation.finish_reasons = [result.stop_reason]

            if getattr(result, "usage", None):
                invocation.input_tokens = result.usage.input_tokens
                invocation.output_tokens = result.usage.output_tokens

            # Parse output message
            invocation.output_messages = [parse_output_message(result)]

            return result

    return traced_method
