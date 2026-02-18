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

from typing import TYPE_CHECKING

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.types import Error, LLMInvocation

from .response_extractors import (
    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
    OPENAI,
    _extract_input_messages,
    _extract_output_type,
    _extract_system_instruction,
    _set_invocation_response_attributes,
)
from .response_wrappers import ResponseStreamWrapper
from .utils import get_llm_request_attributes, is_streaming

if TYPE_CHECKING:
    from opentelemetry.util.genai.handler import TelemetryHandler

__all__ = [
    "responses_create",
    "_set_invocation_response_attributes",
    "GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS",
    "GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS",
]

# ---------------------------------------------------------------------------
# Patch functions
# ---------------------------------------------------------------------------


def responses_create(
    handler: "TelemetryHandler",
    capture_content: bool,
):
    """Wrap the `create` method of the `Responses` class to trace it."""
    # https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L828

    def traced_method(wrapped, instance, args, kwargs):
        if Error is None or LLMInvocation is None:
            raise ModuleNotFoundError(
                "opentelemetry.util.genai.types is unavailable"
            )

        operation_name = GenAIAttributes.GenAiOperationNameValues.CHAT.value
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name,
        )
        output_type = _extract_output_type(kwargs)
        if output_type:
            span_attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = output_type
        request_model = str(
            span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or "unknown"
        )
        streaming = is_streaming(kwargs)

        invocation = handler.start_llm(
            LLMInvocation(
                request_model=request_model,
                operation_name=operation_name,
                provider=OPENAI,
                input_messages=_extract_input_messages(kwargs)
                if capture_content
                else [],
                system_instruction=_extract_system_instruction(kwargs)
                if capture_content
                else [],
                attributes=span_attributes.copy(),
                metric_attributes={
                    GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name
                },
            )
        )

        try:
            result = wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                parsed_result = result.parse()
            else:
                parsed_result = result

            if streaming:
                return ResponseStreamWrapper(
                    parsed_result,
                    handler,
                    invocation,
                    capture_content,
                )

            _set_invocation_response_attributes(
                invocation, parsed_result, capture_content
            )
            handler.stop_llm(invocation)
            return result

        except Exception as error:
            handler.fail_llm(
                invocation, Error(message=str(error), type=type(error))
            )
            raise

    return traced_method
