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

import timeit
from abc import ABC, abstractmethod
from contextvars import Token
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Type, Union

from typing_extensions import TypeAlias

from opentelemetry._logs import Logger
from opentelemetry.context import Context, attach, detach
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import INVALID_SPAN as _INVALID_SPAN
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode

if TYPE_CHECKING:
    from opentelemetry.util.genai.metrics import InvocationMetricsRecorder

ContextToken: TypeAlias = Token[Context]


class ContentCapturingMode(Enum):
    # Do not capture content (default).
    NO_CONTENT = 0
    # Only capture content in spans.
    SPAN_ONLY = 1
    # Only capture content in events.
    EVENT_ONLY = 2
    # Capture content in both spans and events.
    SPAN_AND_EVENT = 3


@dataclass()
class GenericPart:
    """Used for provider-specific message part types that don't match
    the standard MessagePart types defined in semantic conventions. Wrap custom
    types with GenericPart(value=...) to explicitly opt-in to non-standard types.
    This will be removed in a future version when all instrumentations use core types."""

    value: Any
    type: Literal["generic"] = "generic"


@dataclass()
class ToolCallRequest:
    """Represents a tool call requested by the model (message part only).

    Use this for tool calls in message history. For execution tracking with spans
    and metrics, use ToolInvocation instead.

    This model is specified as part of semconv in `GenAI messages Python models - ToolCallRequestPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    arguments: Any
    name: str
    id: str | None
    type: Literal["tool_call"] = "tool_call"


@dataclass()
class ToolCallResponse:
    """Represents a tool call result sent to the model or a built-in tool call outcome and details

    This model is specified as part of semconv in `GenAI messages Python models - ToolCallResponsePart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    response: Any
    id: str | None
    type: Literal["tool_call_response"] = "tool_call_response"


@dataclass()
class ServerToolCall:
    """Represents a server-side tool call.

    Server tool calls are executed by the model provider on the server side rather
    than by the client application. Provider-specific tools (e.g., code_interpreter,
    web_search) can have well-defined schemas defined by the respective providers.

    This model is specified as part of semconv in `GenAI messages Python models - ServerToolCallPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    name: str
    server_tool_call: Any
    id: str | None = None
    type: Literal["server_tool_call"] = "server_tool_call"


@dataclass()
class ServerToolCallResponse:
    """Represents a server-side tool call response.

    Contains the outcome and details of a server tool execution. Provider-specific
    tools (e.g., code_interpreter, web_search) can have well-defined response schemas
    defined by the respective providers.

    This model is specified as part of semconv in `GenAI messages Python models - ServerToolCallResponsePart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    server_tool_call_response: Any
    id: str | None = None
    type: Literal["server_tool_call_response"] = "server_tool_call_response"


@dataclass()
class Text:
    """Represents text content sent to or received from the model

    This model is specified as part of semconv in `GenAI messages Python models - TextPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    content: str
    type: Literal["text"] = "text"


@dataclass()
class Reasoning:
    """Represents reasoning/thinking content received from the model

    This model is specified as part of semconv in `GenAI messages Python models - ReasoningPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    content: str
    type: Literal["reasoning"] = "reasoning"


Modality = Literal["image", "video", "audio"]


@dataclass()
class Blob:
    """Represents blob binary data sent inline to the model

    This model is specified as part of semconv in `GenAI messages Python models - BlobPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    mime_type: str | None
    modality: Union[Modality, str]
    content: bytes
    type: Literal["blob"] = "blob"


@dataclass()
class File:
    """Represents an external referenced file sent to the model by file id

    This model is specified as part of semconv in `GenAI messages Python models - FilePart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    mime_type: str | None
    modality: Union[Modality, str]
    file_id: str
    type: Literal["file"] = "file"


@dataclass()
class Uri:
    """Represents an external referenced file sent to the model by URI

    This model is specified as part of semconv in `GenAI messages Python models - UriPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    mime_type: str | None
    modality: Union[Modality, str]
    uri: str
    type: Literal["uri"] = "uri"


@dataclass()
class FunctionToolDefinition:
    """Represents a function tool definition sent to the model"""

    name: str
    description: str | None
    parameters: Any
    type: Literal["function"] = "function"


@dataclass()
class GenericToolDefinition:
    """Represents a generic tool definition sent to the model"""

    name: str
    type: str


ToolDefinition = Union[FunctionToolDefinition, GenericToolDefinition]

MessagePart = Union[
    Text,
    ToolCallRequest,
    ToolCallResponse,
    ServerToolCall,
    ServerToolCallResponse,
    Blob,
    File,
    Uri,
    Reasoning,
    GenericPart,  # For provider-specific types; prefer standard types above
]


FinishReason = Literal[
    "content_filter", "error", "length", "stop", "tool_calls"
]


@dataclass()
class InputMessage:
    role: str
    parts: list[MessagePart]


@dataclass()
class OutputMessage:
    role: str
    parts: list[MessagePart]
    finish_reason: str | FinishReason


@dataclass
class Error:
    message: str
    type: Type[BaseException]


class GenAIInvocation(ABC):
    """
    Base class for all GenAI invocation types. Manages the lifecycle of a single
    GenAI operation (LLM call, embedding, tool execution, workflow, etc.).

    Use the factory methods on TelemetryHandler (start_inference, start_embedding,
    start_workflow, start_tool) rather than constructing invocations directly.
    """

    def __init__(
        self,
        # Individual components instead of TelemetryHandler to avoid a circular
        # import between handler.py and the invocation modules.
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder | None = None,
        logger: Logger | None = None,
        *,
        operation_name: str,
        span_name: str,
        span_kind: SpanKind = SpanKind.CLIENT,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        self._tracer = tracer
        self._metrics_recorder = metrics_recorder
        self._logger = logger
        self._operation_name: str = operation_name
        self.attributes: dict[str, Any] = (
            {} if attributes is None else attributes
        )
        """Additional attributes to set on spans and/or events. Not set on metrics."""
        self.metric_attributes: dict[str, Any] = (
            {} if metric_attributes is None else metric_attributes
        )
        """Additional attributes to set on metrics. Must be low cardinality. Not set on spans or events."""
        self.span: Span = _INVALID_SPAN
        self._span_context: Context
        self._span_name: str = span_name
        self._span_kind: SpanKind = span_kind
        self._context_token: ContextToken | None = None
        self._monotonic_start_s: float | None = None

    def _start(self) -> None:
        """Start the invocation span and attach it to the current context."""
        self.span = self._tracer.start_span(
            name=self._span_name,
            kind=self._span_kind,
        )
        self._span_context = set_span_in_context(self.span)
        self._monotonic_start_s = timeit.default_timer()
        self._context_token = attach(self._span_context)

    def _get_metric_attributes(self) -> dict[str, Any]:
        """Return low-cardinality attributes for metric recording."""
        return dict(self.metric_attributes)

    def _get_metric_token_counts(self) -> dict[str, int]:  # pylint: disable=no-self-use
        """Return {token_type: count} for token histogram recording."""
        return {}

    def _apply_error_attributes(self, error: Error) -> None:
        """Apply error status and error.type attribute to the span, events, and metrics."""
        error_type = error.type.__qualname__
        self.span.set_status(Status(StatusCode.ERROR, error.message))
        self.attributes[error_attributes.ERROR_TYPE] = error_type
        self.metric_attributes[error_attributes.ERROR_TYPE] = error_type

    @abstractmethod
    def _apply_finish(self, error: Error | None = None) -> None:
        """Apply finish telemetry (attributes, metrics, events)."""

    def _finish(self, error: Error | None = None) -> None:
        """Apply finish telemetry and end the span."""
        if self._context_token is None:
            return
        try:
            self._apply_finish(error)
        finally:
            try:
                detach(self._context_token)
            except Exception:  # pylint: disable=broad-except
                pass
            self.span.end()

    def stop(self) -> None:
        """Finalize the invocation successfully and end its span."""
        self._finish()

    def fail(self, error: Error | BaseException) -> None:
        """Fail the invocation and end its span with error status."""
        if isinstance(error, BaseException):
            error = Error(type=type(error), message=str(error))
        self._finish(error)


def __getattr__(name: str) -> object:
    if name == "LLMInvocation":
        from opentelemetry.util.genai.inference_invocation import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            LLMInvocation,  # pyright: ignore[reportDeprecated]
        )

        return LLMInvocation  # pyright: ignore[reportDeprecated]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
