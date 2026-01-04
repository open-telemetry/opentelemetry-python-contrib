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

from contextlib import contextmanager
from dataclasses import asdict
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Literal,
    MutableSequence,
    Union,
    cast,
    overload,
)

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.instrumentation._semconv import (
    _StabilityMode,
)
from opentelemetry.instrumentation.vertexai.utils import (
    GenerateContentParams,
    _map_finish_reason,
    convert_content_to_message_parts,
    get_genai_request_attributes,
    get_genai_response_attributes,
    get_server_attributes,
    get_span_name,
    request_to_events,
    response_to_events,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    InputMessage,
    OutputMessage,
)
from opentelemetry.util.genai.utils import gen_ai_json_dumps

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


# For details about GEN_AI_LATEST_EXPERIMENTAL stability mode see
# https://github.com/open-telemetry/semantic-conventions/blob/v1.37.0/docs/gen-ai/gen-ai-agent-spans.md?plain=1#L18-L37
class MethodWrappers:
    @overload
    def __init__(
        self,
        tracer: Tracer,
        logger: Logger,
        capture_content: ContentCapturingMode,
        sem_conv_opt_in_mode: Literal[
            _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
        ],
        completion_hook: CompletionHook,
    ) -> None: ...

    @overload
    def __init__(
        self,
        tracer: Tracer,
        logger: Logger,
        capture_content: bool,
        sem_conv_opt_in_mode: Literal[_StabilityMode.DEFAULT],
        completion_hook: CompletionHook,
    ) -> None: ...

    def __init__(
        self,
        tracer: Tracer,
        logger: Logger,
        capture_content: Union[bool, ContentCapturingMode],
        sem_conv_opt_in_mode: Union[
            Literal[_StabilityMode.DEFAULT],
            Literal[_StabilityMode.GEN_AI_LATEST_EXPERIMENTAL],
        ],
        completion_hook: CompletionHook,
    ) -> None:
        self.tracer = tracer
        self.logger = logger
        self.capture_content = capture_content
        self.sem_conv_opt_in_mode = sem_conv_opt_in_mode
        self.completion_hook = completion_hook

    @contextmanager
    def _with_new_instrumentation(
        self,
        capture_content: ContentCapturingMode,
        instance: client.PredictionServiceClient
        | client_v1beta1.PredictionServiceClient,
        args: Any,
        kwargs: Any,
    ):
        params = _extract_params(*args, **kwargs)
        request_attributes = get_genai_request_attributes(True, params)
        with self.tracer.start_as_current_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {request_attributes.get(GenAI.GEN_AI_REQUEST_MODEL, '')}".strip(),
            kind=SpanKind.CLIENT,
        ) as span:

            def handle_response(
                response: prediction_service.GenerateContentResponse
                | prediction_service_v1beta1.GenerateContentResponse
                | None,
            ) -> None:
                attributes = (
                    get_server_attributes(instance.api_endpoint)  # type: ignore[reportUnknownMemberType]
                    | request_attributes
                    | get_genai_response_attributes(response)
                )
                event = LogRecord(
                    event_name="gen_ai.client.inference.operation.details",
                )
                event.attributes = attributes.copy()
                system_instructions, inputs, outputs = [], [], []
                if params.system_instruction:
                    system_instructions = convert_content_to_message_parts(
                        params.system_instruction
                    )
                if params.contents:
                    inputs = [
                        InputMessage(
                            role=content.role,
                            parts=convert_content_to_message_parts(content),
                        )
                        for content in params.contents
                    ]
                if response:
                    outputs = [
                        OutputMessage(
                            finish_reason=_map_finish_reason(
                                candidate.finish_reason
                            ),
                            role=candidate.content.role,
                            parts=convert_content_to_message_parts(
                                candidate.content
                            ),
                        )
                        for candidate in response.candidates
                    ]
                self.completion_hook.on_completion(
                    inputs=inputs,
                    outputs=outputs,
                    system_instruction=system_instructions,
                    span=span,
                    log_record=event,
                )
                content_attributes = {
                    k: [asdict(x) for x in v]
                    for k, v in [
                        (
                            GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
                            system_instructions,
                        ),
                        (GenAI.GEN_AI_INPUT_MESSAGES, inputs),
                        (GenAI.GEN_AI_OUTPUT_MESSAGES, outputs),
                    ]
                    if v
                }
                if span.is_recording():
                    span.set_attributes(attributes)
                    if capture_content in (
                        ContentCapturingMode.SPAN_AND_EVENT,
                        ContentCapturingMode.SPAN_ONLY,
                    ):
                        span.set_attributes(
                            {
                                k: gen_ai_json_dumps(v)
                                for k, v in content_attributes.items()
                            }
                        )
                if capture_content in (
                    ContentCapturingMode.SPAN_AND_EVENT,
                    ContentCapturingMode.EVENT_ONLY,
                ):
                    event.attributes |= content_attributes
                self.logger.emit(event)

            yield handle_response

    @contextmanager
    def _with_default_instrumentation(
        self,
        capture_content: bool,
        instance: client.PredictionServiceClient
        | client_v1beta1.PredictionServiceClient,
        args: Any,
        kwargs: Any,
    ):
        params = _extract_params(*args, **kwargs)
        api_endpoint: str = instance.api_endpoint  # type: ignore[reportUnknownMemberType]
        span_attributes = {
            **get_genai_request_attributes(False, params),
            **get_server_attributes(api_endpoint),
        }

        span_name = get_span_name(span_attributes)

        with self.tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as span:
            for event in request_to_events(
                params=params, capture_content=capture_content
            ):
                self.logger.emit(event)

            # TODO: set error.type attribute
            # https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md

            def handle_response(
                response: prediction_service.GenerateContentResponse
                | prediction_service_v1beta1.GenerateContentResponse,
            ) -> None:
                if span.is_recording():
                    # When streaming, this is called multiple times so attributes would be
                    # overwritten. In practice, it looks the API only returns the interesting
                    # attributes on the last streamed response. However, I couldn't find
                    # documentation for this and setting attributes shouldn't be too expensive.
                    span.set_attributes(
                        get_genai_response_attributes(response)
                    )

                for event in response_to_events(
                    response=response, capture_content=capture_content
                ):
                    self.logger.emit(event)

            yield handle_response

    def generate_content(
        self,
        wrapped: Callable[
            ...,
            prediction_service.GenerateContentResponse
            | prediction_service_v1beta1.GenerateContentResponse,
        ],
        instance: client.PredictionServiceClient
        | client_v1beta1.PredictionServiceClient,
        args: Any,
        kwargs: Any,
    ) -> (
        prediction_service.GenerateContentResponse
        | prediction_service_v1beta1.GenerateContentResponse
    ):
        if self.sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
            capture_content_bool = cast(bool, self.capture_content)
            with self._with_default_instrumentation(
                capture_content_bool, instance, args, kwargs
            ) as handle_response:
                response = wrapped(*args, **kwargs)
                handle_response(response)
                return response
        else:
            capture_content = cast(ContentCapturingMode, self.capture_content)
            with self._with_new_instrumentation(
                capture_content, instance, args, kwargs
            ) as handle_response:
                response = None
                try:
                    response = wrapped(*args, **kwargs)
                    return response
                finally:
                    handle_response(response)

    async def agenerate_content(
        self,
        wrapped: Callable[
            ...,
            Awaitable[
                prediction_service.GenerateContentResponse
                | prediction_service_v1beta1.GenerateContentResponse
            ],
        ],
        instance: client.PredictionServiceClient
        | client_v1beta1.PredictionServiceClient,
        args: Any,
        kwargs: Any,
    ) -> (
        prediction_service.GenerateContentResponse
        | prediction_service_v1beta1.GenerateContentResponse
    ):
        if self.sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
            capture_content_bool = cast(bool, self.capture_content)
            with self._with_default_instrumentation(
                capture_content_bool, instance, args, kwargs
            ) as handle_response:
                response = await wrapped(*args, **kwargs)
                handle_response(response)
                return response
        else:
            capture_content = cast(ContentCapturingMode, self.capture_content)
            with self._with_new_instrumentation(
                capture_content, instance, args, kwargs
            ) as handle_response:
                response = None
                try:
                    response = await wrapped(*args, **kwargs)
                    return response
                finally:
                    handle_response(response)
