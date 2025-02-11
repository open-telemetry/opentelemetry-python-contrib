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
    MutableSequence,
)

from opentelemetry._events import EventLogger
from opentelemetry.instrumentation.vertexai.utils import (
    GenerateContentParams,
    get_genai_request_attributes,
    get_genai_response_attributes,
    get_server_attributes,
    get_span_name,
    request_to_events,
    response_to_events,
)
from opentelemetry.trace import SpanKind, Tracer

if TYPE_CHECKING:
    from google.cloud.aiplatform_v1.services.prediction_service import client
    from google.cloud.aiplatform_v1.types import (
        content,
        prediction_service,
    )
    from google.cloud.aiplatform_v1beta1.services.prediction_service import (
        client as client_v1beta1,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        content as content_v1beta1,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        prediction_service as prediction_service_v1beta1,
    )


# Use parameter signature from
# https://github.com/googleapis/python-aiplatform/blob/v1.76.0/google/cloud/aiplatform_v1/services/prediction_service/client.py#L2088
# to handle named vs positional args robustly
def _extract_params(
    request: prediction_service.GenerateContentRequest
    | prediction_service_v1beta1.GenerateContentRequest
    | dict[Any, Any]
    | None = None,
    *,
    model: str | None = None,
    contents: MutableSequence[content.Content]
    | MutableSequence[content_v1beta1.Content]
    | None = None,
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
            ...,
            prediction_service.GenerateContentResponse
            | prediction_service_v1beta1.GenerateContentResponse,
        ],
        instance: client.PredictionServiceClient
        | client_v1beta1.PredictionServiceClient,
        args: Any,
        kwargs: Any,
    ):
        params = _extract_params(*args, **kwargs)
        api_endpoint: str = instance.api_endpoint  # type: ignore[reportUnknownMemberType]
        span_attributes = {
            **get_genai_request_attributes(params),
            **get_server_attributes(api_endpoint),
        }

        span_name = get_span_name(span_attributes)
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as span:
            for event in request_to_events(
                params=params, capture_content=capture_content
            ):
                event_logger.emit(event)

            # TODO: set error.type attribute
            # https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md
            response = wrapped(*args, **kwargs)
            # TODO: handle streaming
            # if is_streaming(kwargs):
            #     return StreamWrapper(
            #         result, span, event_logger, capture_content
            #     )

            if span.is_recording():
                span.set_attributes(get_genai_response_attributes(response))
            for event in response_to_events(
                response=response, capture_content=capture_content
            ):
                event_logger.emit(event)

            return response

    return traced_method
