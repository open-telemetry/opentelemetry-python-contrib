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

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    MutableSequence,
    Optional,
    Union,
)

from opentelemetry._events import EventLogger
from opentelemetry.instrumentation.vertexai.utils import (
    GenerateContentParams,
    get_genai_request_attributes,
    get_span_name,
)
from opentelemetry.trace import SpanKind, Tracer

if TYPE_CHECKING:
    from google.cloud.aiplatform_v1.types import (
        content,
        prediction_service,
    )
    from vertexai.generative_models import (
        GenerationResponse,
    )
    from vertexai.generative_models._generative_models import (
        _GenerativeModel,
    )


# Use parameter signature from
# https://github.com/googleapis/python-aiplatform/blob/v1.76.0/google/cloud/aiplatform_v1/services/prediction_service/client.py#L2088
# to handle named vs positional args robustly
def _extract_params(
    request: Optional[
        Union[prediction_service.GenerateContentRequest, dict[Any, Any]]
    ] = None,
    *,
    model: Optional[str] = None,
    contents: Optional[MutableSequence[content.Content]] = None,
    **_kwargs: Any,
) -> GenerateContentParams:
    # Request vs the named parameters are mututally exclusive or the RPC will fail
    if not request:
        return GenerateContentParams(
            model=model or "",
            contents=contents,
        )

    if isinstance(request, dict):
        return GenerateContentParams(**request)

    return GenerateContentParams(
        model=request.model,
        contents=request.contents,
        system_instruction=request.system_instruction,
        tools=request.tools,
        tool_config=request.tool_config,
        labels=request.labels,
        safety_settings=request.safety_settings,
        generation_config=request.generation_config,
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
        params = _extract_params(*args, **kwargs)
        span_attributes = get_genai_request_attributes(params)

        span_name = get_span_name(span_attributes)
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as _span:
            # TODO: emit request events
            # if span.is_recording():
            #     for message in kwargs.get("messages", []):
            #         event_logger.emit(
            #             message_to_event(message, capture_content)
            #         )

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
            return result

    return traced_method
