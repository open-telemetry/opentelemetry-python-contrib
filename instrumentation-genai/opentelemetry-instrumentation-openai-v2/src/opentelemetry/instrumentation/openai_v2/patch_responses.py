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

from __future__ import annotations

from typing import Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import ContentCapturingMode, Error

from .instruments import Instruments
from .response_extractors import (
    _create_invocation as create_response_invocation,
    _set_invocation_response_attributes,
)
from .response_wrappers import AsyncResponseStreamWrapper, ResponseStreamWrapper
from .utils import is_streaming


def responses_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap the `create` method of the `Responses` class to trace it."""

    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_response_invocation(
                kwargs, instance, capture_content=capture_content
            )
        )

        try:
            result = wrapped(*args, **kwargs)
            parsed_result = _get_response_stream_result(result)

            if is_streaming(kwargs):
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
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def async_responses_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap the `create` method of the `AsyncResponses` class to trace it."""

    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    async def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_response_invocation(
                kwargs, instance, capture_content=capture_content
            )
        )

        try:
            result = await wrapped(*args, **kwargs)
            parsed_result = _get_response_stream_result(result)

            if is_streaming(kwargs):
                return AsyncResponseStreamWrapper(
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
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def _get_response_stream_result(result):
    if hasattr(result, "parse"):
        return result.parse()
    return result


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
):
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: (
            GenAIAttributes.GenAiOperationNameValues.CHAT.value
        ),
        GenAIAttributes.GEN_AI_SYSTEM: (
            GenAIAttributes.GenAiSystemValues.OPENAI.value
        ),
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if error_type:
        common_attributes["error.type"] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if result and getattr(result, "service_tier", None):
        common_attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
        ] = result.service_tier

    if ServerAttributes.SERVER_ADDRESS in request_attributes:
        common_attributes[ServerAttributes.SERVER_ADDRESS] = (
            request_attributes[ServerAttributes.SERVER_ADDRESS]
        )

    if ServerAttributes.SERVER_PORT in request_attributes:
        common_attributes[ServerAttributes.SERVER_PORT] = request_attributes[
            ServerAttributes.SERVER_PORT
        ]

    instruments.operation_duration_histogram.record(
        duration,
        attributes=common_attributes,
    )

    if result and getattr(result, "usage", None):
        input_tokens = getattr(result.usage, "input_tokens", None)
        output_tokens = getattr(result.usage, "output_tokens", None)

        if input_tokens is not None:
            input_attributes = {
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: (
                    GenAIAttributes.GenAiTokenTypeValues.INPUT.value
                ),
            }
            instruments.token_usage_histogram.record(
                input_tokens,
                attributes=input_attributes,
            )

        if output_tokens is not None:
            output_attributes = {
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: (
                    GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
                ),
            }
            instruments.token_usage_histogram.record(
                output_tokens,
                attributes=output_attributes,
            )
