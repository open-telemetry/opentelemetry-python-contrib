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

from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional

from opentelemetry._events import EventLogger
from opentelemetry.instrumentation.vertexai.utils import (
    GenerateContentParams,
    get_genai_request_attributes,
    get_span_name,
    handle_span_exception,
)
from opentelemetry.trace import SpanKind, Tracer

if TYPE_CHECKING:
    from vertexai.generative_models import (
        GenerationResponse,
        Tool,
        ToolConfig,
    )
    from vertexai.generative_models._generative_models import (
        ContentsType,
        GenerationConfigType,
        SafetySettingsType,
        _GenerativeModel,
    )


def generate_content_create(
    tracer: Tracer, event_logger: EventLogger, capture_content: bool
):
    """Wrap the `generate_content` method of the `GenerativeModel` class to trace it."""

    def traced_method(
        wrapped: Callable[
            ..., GenerationResponse | Iterable[GenerationResponse]
        ],
        instance: _GenerativeModel,
        args: Any,
        kwargs: Any,
    ):
        # Use parameter signature from
        # https://github.com/googleapis/python-aiplatform/blob/v1.76.0/vertexai/generative_models/_generative_models.py#L595
        # to handle named vs positional args robustly
        def extract_params(
            contents: ContentsType,
            *,
            generation_config: Optional[GenerationConfigType] = None,
            safety_settings: Optional[SafetySettingsType] = None,
            tools: Optional[list[Tool]] = None,
            tool_config: Optional[ToolConfig] = None,
            labels: Optional[dict[str, str]] = None,
            stream: bool = False,
            **_kwargs: Any,
        ) -> GenerateContentParams:
            return GenerateContentParams(
                contents=contents,
                generation_config=generation_config,
                safety_settings=safety_settings,
                tools=tools,
                tool_config=tool_config,
                labels=labels,
                stream=stream,
            )

        params = extract_params(*args, **kwargs)

        span_attributes = get_genai_request_attributes(instance, params)

        span_name = get_span_name(span_attributes)
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # TODO: emit request events
            # if span.is_recording():
            #     for message in kwargs.get("messages", []):
            #         event_logger.emit(
            #             message_to_event(message, capture_content)
            #         )

            try:
                result = wrapped(*args, **kwargs)
                # TODO: handle streaming
                # if is_streaming(kwargs):
                #     return StreamWrapper(
                #         result, span, event_logger, capture_content
                #     )

                # TODO: add response attributes and events
                # if span.is_recording():
                #     _set_response_attributes(
                #         span, result, event_logger, capture_content
                #     )
                span.end()
                return result

            except Exception as error:
                handle_span_exception(span, error)
                raise

    return traced_method
