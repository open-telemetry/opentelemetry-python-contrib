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
from contextlib import contextmanager
from contextvars import Token
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Iterator, Sequence

from typing_extensions import Self, TypeAlias

from opentelemetry._logs import Logger
from opentelemetry.context import Context, attach, detach
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import INVALID_SPAN as _INVALID_SPAN
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    MessagePart,
    OutputMessage,
    ToolDefinition,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
)

if TYPE_CHECKING:
    from opentelemetry.util.genai.metrics import InvocationMetricsRecorder

ContextToken: TypeAlias = Token[Context]


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
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
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
        return self.metric_attributes

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

    @contextmanager
    def _managed(self) -> Iterator[Self]:
        """Context manager that calls stop() on success or fail() on exception."""
        try:
            yield self
        except Exception as exc:
            self.fail(exc)
            raise
        self.stop()


def get_content_attributes(
    *,
    input_messages: Sequence[InputMessage],
    output_messages: Sequence[OutputMessage],
    system_instruction: Sequence[MessagePart],
    tool_definitions: Sequence[ToolDefinition] | None,
    for_span: bool,
) -> dict[str, Any]:
    """Serialize messages, system instructions, and tool definitions into attributes.

    Args:
        input_messages: Input messages to serialize.
        output_messages: Output messages to serialize.
        system_instruction: System instructions to serialize.
        tool_definitions: Tool definitions to serialize (may be None).
        for_span: If True, serialize for span attributes (JSON string);
                  if False, serialize for event attributes (list of dicts).
    """
    if not is_experimental_mode():
        return {}

    mode = get_content_capturing_mode()
    allowed_modes = (
        (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
        if for_span
        else (
            ContentCapturingMode.EVENT_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
    )
    if mode not in allowed_modes:
        return {}

    def serialize(items: Sequence[Any]) -> Any:
        dicts = [asdict(item) for item in items]
        return gen_ai_json_dumps(dicts) if for_span else dicts

    optional_attrs = (
        (
            GenAI.GEN_AI_INPUT_MESSAGES,
            serialize(input_messages) if input_messages else None,
        ),
        (
            GenAI.GEN_AI_OUTPUT_MESSAGES,
            serialize(output_messages) if output_messages else None,
        ),
        (
            GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
            serialize(system_instruction) if system_instruction else None,
        ),
        (
            GenAI.GEN_AI_TOOL_DEFINITIONS,
            serialize(tool_definitions) if tool_definitions else None,
        ),
    )
    return {key: value for key, value in optional_attrs if value is not None}
