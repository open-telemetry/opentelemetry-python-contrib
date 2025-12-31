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

"""
High-level API wrappers for Vertex AI TextGenerationModel and ChatSession.

These APIs use different backends than the PredictionServiceClient that is
instrumented in patch.py, so they need separate instrumentation.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Generator,
    Literal,
    Union,
    cast,
    overload,
)

from opentelemetry._logs import Logger
from opentelemetry.instrumentation._semconv import (
    _StabilityMode,
)
from opentelemetry.instrumentation.vertexai.events import (
    ChoiceMessage,
    choice_event,
    user_event,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.types import ContentCapturingMode

if TYPE_CHECKING:
    from vertexai.language_models import (
        ChatSession as LegacyChatSession,
    )
    from vertexai.language_models import (
        TextGenerationModel,
        TextGenerationResponse,
    )


# Methods to wrap for TextGenerationModel
TEXT_GENERATION_METHODS = [
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict",
        "is_async": False,
        "is_streaming": False,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_async",
        "is_async": True,
        "is_streaming": False,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_streaming",
        "is_async": False,
        "is_streaming": True,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_streaming_async",
        "is_async": True,
        "is_streaming": True,
    },
]

# Methods for legacy ChatSession (language_models, not generative_models)
LEGACY_CHAT_SESSION_METHODS = [
    {
        "package": "vertexai.language_models",
        "object": "ChatSession",
        "method": "send_message",
        "is_async": False,
        "is_streaming": False,
    },
    {
        "package": "vertexai.language_models",
        "object": "ChatSession",
        "method": "send_message_streaming",
        "is_async": False,
        "is_streaming": True,
    },
]


@dataclass(frozen=True)
class TextGenerationParams:
    """Parameters extracted from TextGenerationModel.predict calls."""

    model: str
    prompt: str | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None


def _extract_model_name(instance: Any) -> str:
    """Extract model name from TextGenerationModel or ChatSession instance."""
    # TextGenerationModel has _model_id
    if hasattr(instance, "_model_id"):
        return instance._model_id
    # ChatSession has _model reference
    if hasattr(instance, "_model") and hasattr(instance._model, "_model_id"):
        return instance._model._model_id
    return "unknown"


def _extract_text_generation_params(
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> TextGenerationParams:
    """Extract parameters from TextGenerationModel.predict call."""
    model = _extract_model_name(instance)

    # predict(prompt, *, max_output_tokens=None, temperature=None, ...)
    prompt = args[0] if args else kwargs.get("prompt")

    return TextGenerationParams(
        model=model,
        prompt=prompt,
        max_output_tokens=kwargs.get("max_output_tokens"),
        temperature=kwargs.get("temperature"),
        top_k=kwargs.get("top_k"),
        top_p=kwargs.get("top_p"),
        stop_sequences=kwargs.get("stop_sequences"),
    )


def _get_request_attributes(
    params: TextGenerationParams,
) -> dict[str, Any]:
    """Get span attributes from request parameters."""
    attributes: dict[str, Any] = {
        GenAI.GEN_AI_OPERATION_NAME: GenAI.GenAiOperationNameValues.CHAT.value,
        GenAI.GEN_AI_REQUEST_MODEL: params.model,
        GenAI.GEN_AI_SYSTEM: GenAI.GenAiSystemValues.VERTEX_AI.value,
    }

    if params.temperature is not None:
        attributes[GenAI.GEN_AI_REQUEST_TEMPERATURE] = params.temperature
    if params.top_p is not None:
        attributes[GenAI.GEN_AI_REQUEST_TOP_P] = params.top_p
    if params.max_output_tokens is not None:
        attributes[GenAI.GEN_AI_REQUEST_MAX_TOKENS] = params.max_output_tokens
    if params.stop_sequences:
        attributes[GenAI.GEN_AI_REQUEST_STOP_SEQUENCES] = tuple(
            params.stop_sequences
        )

    return attributes


def _get_response_attributes(
    response: TextGenerationResponse | None,
) -> dict[str, Any]:
    """Get span attributes from response."""
    if not response:
        return {}

    attributes: dict[str, Any] = {}

    # TextGenerationResponse has safety_attributes, not finish_reason
    # Map is_blocked to finish_reason
    if hasattr(response, "is_blocked") and response.is_blocked:
        attributes[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] = ("content_filter",)
    else:
        attributes[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] = ("stop",)

    return attributes


def _map_finish_reason(response: TextGenerationResponse | None) -> str:
    """Map TextGenerationResponse to finish reason."""
    if not response:
        return "error"
    if hasattr(response, "is_blocked") and response.is_blocked:
        return "content_filter"
    return "stop"


class HighLevelMethodWrappers:
    """Wrappers for high-level Vertex AI APIs (TextGenerationModel)."""

    @overload
    def __init__(
        self,
        tracer: Tracer,
        logger: Logger,
        capture_content: ContentCapturingMode,
        sem_conv_opt_in_mode: Literal[
            _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
        ],
    ) -> None: ...

    @overload
    def __init__(
        self,
        tracer: Tracer,
        logger: Logger,
        capture_content: bool,
        sem_conv_opt_in_mode: Literal[_StabilityMode.DEFAULT],
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
    ) -> None:
        self.tracer = tracer
        self.logger = logger
        self.capture_content = capture_content
        self.sem_conv_opt_in_mode = sem_conv_opt_in_mode

    @contextmanager
    def _with_instrumentation(
        self,
        instance: TextGenerationModel | LegacyChatSession,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Generator[Callable[[TextGenerationResponse | None], None], None, None]:
        """Context manager for instrumenting text generation calls."""
        params = _extract_text_generation_params(instance, args, kwargs)
        span_attributes = _get_request_attributes(params)
        span_name = f"{span_attributes[GenAI.GEN_AI_OPERATION_NAME]} {params.model}"

        with self.tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as span:
            # Emit user event for the prompt
            if self.sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
                capture_content = cast(bool, self.capture_content)
            else:
                capture_content = self.capture_content in (
                    ContentCapturingMode.SPAN_AND_EVENT,
                    ContentCapturingMode.EVENT_ONLY,
                )

            if params.prompt:
                self.logger.emit(
                    user_event(
                        role="user",
                        content=[{"text": params.prompt}]
                        if capture_content
                        else None,
                    )
                )

            def handle_response(
                response: TextGenerationResponse | None,
            ) -> None:
                if span.is_recording():
                    span.set_attributes(_get_response_attributes(response))
                    if response:
                        span.set_status(Status(StatusCode.OK))
                    else:
                        span.set_status(Status(StatusCode.ERROR))

                # Emit choice event
                response_text = response.text if response else None
                self.logger.emit(
                    choice_event(
                        finish_reason=_map_finish_reason(response),
                        index=0,
                        message=ChoiceMessage(
                            role="model",
                            content=[{"text": response_text}]
                            if capture_content and response_text
                            else None,
                        ),
                    )
                )

            yield handle_response

    def _build_streaming_response(
        self,
        response: Generator[TextGenerationResponse, None, None],
        handle_response: Callable[[TextGenerationResponse | None], None],
    ) -> Generator[TextGenerationResponse, None, None]:
        """Wrap streaming response to capture completion."""
        complete_response = None
        for chunk in response:
            complete_response = chunk
            yield chunk
        handle_response(complete_response)

    async def _abuild_streaming_response(
        self,
        response: Any,  # AsyncGenerator
        handle_response: Callable[[TextGenerationResponse | None], None],
    ):
        """Wrap async streaming response to capture completion."""
        complete_response = None
        async for chunk in response:
            complete_response = chunk
            yield chunk
        handle_response(complete_response)

    def predict(
        self,
        wrapped: Callable[..., TextGenerationResponse],
        instance: TextGenerationModel,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> TextGenerationResponse:
        """Wrapper for TextGenerationModel.predict."""
        with self._with_instrumentation(
            instance, args, kwargs
        ) as handle_response:
            try:
                response = wrapped(*args, **kwargs)
                handle_response(response)
                return response
            except Exception:
                handle_response(None)
                raise

    async def apredict(
        self,
        wrapped: Callable[..., Awaitable[TextGenerationResponse]],
        instance: TextGenerationModel,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> TextGenerationResponse:
        """Wrapper for TextGenerationModel.predict_async."""
        with self._with_instrumentation(
            instance, args, kwargs
        ) as handle_response:
            try:
                response = await wrapped(*args, **kwargs)
                handle_response(response)
                return response
            except Exception:
                handle_response(None)
                raise

    def predict_streaming(
        self,
        wrapped: Callable[
            ..., Generator[TextGenerationResponse, None, None]
        ],
        instance: TextGenerationModel,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Generator[TextGenerationResponse, None, None]:
        """Wrapper for TextGenerationModel.predict_streaming."""
        with self._with_instrumentation(
            instance, args, kwargs
        ) as handle_response:
            response = wrapped(*args, **kwargs)
            return self._build_streaming_response(response, handle_response)

    async def apredict_streaming(
        self,
        wrapped: Callable[..., Any],  # Returns AsyncGenerator
        instance: TextGenerationModel,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ):
        """Wrapper for TextGenerationModel.predict_streaming_async."""
        with self._with_instrumentation(
            instance, args, kwargs
        ) as handle_response:
            response = await wrapped(*args, **kwargs)
            return self._abuild_streaming_response(response, handle_response)

    def send_message(
        self,
        wrapped: Callable[..., TextGenerationResponse],
        instance: LegacyChatSession,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> TextGenerationResponse:
        """Wrapper for legacy ChatSession.send_message."""
        # ChatSession.send_message has same signature as predict
        return self.predict(wrapped, instance, args, kwargs)

    def send_message_streaming(
        self,
        wrapped: Callable[
            ..., Generator[TextGenerationResponse, None, None]
        ],
        instance: LegacyChatSession,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Generator[TextGenerationResponse, None, None]:
        """Wrapper for legacy ChatSession.send_message_streaming."""
        return self.predict_streaming(wrapped, instance, args, kwargs)
