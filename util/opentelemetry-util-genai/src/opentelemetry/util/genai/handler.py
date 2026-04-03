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
Telemetry handler for GenAI invocations.

This module exposes the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data (spans and related attributes).

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage:
    handler = get_telemetry_handler()

    # Factory method: construct and start in one call, then stop or fail.
    invocation = handler.start_inference("my-provider", request_model="my-model")
    invocation.input_messages = [...]
    invocation.temperature = 0.7
    try:
        # ... call the underlying library ...
        invocation.output_messages = [...]
        invocation.stop()
    except Exception as exc:
        invocation.fail(exc)
        raise

    # Or use the context manager form — exception handling is automatic.
    with handler.inference("my-provider", request_model="my-model") as invocation:
        invocation.input_messages = [...]
        # ... call the underlying library ...
        invocation.output_messages = [...]
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from typing_extensions import deprecated

from opentelemetry._logs import (
    LoggerProvider,
    get_logger,
)
from opentelemetry.metrics import MeterProvider, get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import (
    TracerProvider,
    get_tracer,
)
from opentelemetry.util.genai._invocation import Error
from opentelemetry.util.genai.embedding_invocation import EmbeddingInvocation
from opentelemetry.util.genai.inference_invocation import (
    InferenceInvocation,
    LLMInvocation,  # pyright: ignore[reportDeprecated]
)
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.tool_invocation import ToolInvocation
from opentelemetry.util.genai.version import __version__
from opentelemetry.util.genai.workflow_invocation import WorkflowInvocation


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(
        self,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        logger_provider: LoggerProvider | None = None,
    ):
        schema_url = Schemas.V1_37_0.value
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=schema_url,
        )
        meter = get_meter(
            __name__, meter_provider=meter_provider, schema_url=schema_url
        )
        self._metrics_recorder = InvocationMetricsRecorder(meter)
        self._logger = get_logger(
            __name__,
            __version__,
            logger_provider,
            schema_url=schema_url,
        )

    # New-style factory methods: construct + start in one call, handler stored on invocation

    def start_inference(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
    ) -> InferenceInvocation:
        """Create and start an LLM inference invocation.

        Set remaining attributes (input_messages, temperature, etc.) on the
        returned invocation, then call invocation.stop() or invocation.fail().
        """
        return InferenceInvocation(
            self._tracer,
            self._metrics_recorder,
            self._logger,
            provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
        )

    @deprecated(
        "handler.start_llm() is deprecated. Use handler.start_inference() instead."
    )
    def start_llm(self, invocation: LLMInvocation) -> LLMInvocation:  # pyright: ignore[reportDeprecated]
        """Start an LLM invocation.

        .. deprecated::
            Use ``handler.start_inference()`` instead.
        """
        if invocation._context_token is not None:
            # Already started (e.g. tracer passed to LLMInvocation.__init__)
            return invocation
        invocation._start_with_handler(
            self._tracer, self._metrics_recorder, self._logger
        )
        return invocation

    def start_embedding(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
    ) -> EmbeddingInvocation:
        """Create and start an Embedding invocation.

        Set remaining attributes (encoding_formats, etc.) on the returned
        invocation, then call invocation.stop() or invocation.fail().
        """
        return EmbeddingInvocation(
            self._tracer,
            self._metrics_recorder,
            self._logger,
            provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
        )

    def start_tool(
        self,
        name: str,
        *,
        arguments: object = None,
        tool_call_id: str | None = None,
        tool_type: str | None = None,
        tool_description: str | None = None,
    ) -> ToolInvocation:
        """Create and start a tool invocation.

        Set tool_result on the returned invocation when done, then call
        invocation.stop() or invocation.fail().
        """
        return ToolInvocation(
            self._tracer,
            self._metrics_recorder,
            self._logger,
            name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            tool_type=tool_type,
            tool_description=tool_description,
        )

    def start_workflow(
        self,
        *,
        name: str | None = None,
    ) -> WorkflowInvocation:
        """Create and start a workflow invocation.

        Set remaining attributes on the returned invocation, then call
        invocation.stop() or invocation.fail().
        """
        return WorkflowInvocation(
            self._tracer, self._metrics_recorder, self._logger, name
        )

    @deprecated(
        "handler.stop_llm() is deprecated. Use invocation.stop() instead."
    )
    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:  # pylint: disable=no-self-use  # pyright: ignore[reportDeprecated]
        """Finalize an LLM invocation successfully and end its span.

        .. deprecated::
            Use ``invocation.stop()`` instead.
        """
        invocation.stop()
        return invocation

    @deprecated(
        "handler.fail_llm() is deprecated. Use invocation.fail(error) instead."
    )
    def fail_llm(  # pylint: disable=no-self-use
        self,
        invocation: LLMInvocation,  # pyright: ignore[reportDeprecated]
        error: Error,
    ) -> LLMInvocation:  # pyright: ignore[reportDeprecated]
        """Fail an LLM invocation and end its span with error status.

        .. deprecated::
            Use ``invocation.fail(error)`` instead.
        """
        invocation.fail(error)
        return invocation

    @contextmanager
    def inference(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
    ) -> Iterator[InferenceInvocation]:
        """Context manager for LLM inference invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        invocation = self.start_inference(
            provider=provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
        )
        try:
            yield invocation
        except Exception as exc:
            invocation.fail(exc)
            raise
        invocation.stop()

    @contextmanager
    def embedding(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
    ) -> Iterator[EmbeddingInvocation]:
        """Context manager for Embedding invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        invocation = self.start_embedding(
            provider=provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
        )
        try:
            yield invocation
        except Exception as exc:
            invocation.fail(exc)
            raise
        invocation.stop()

    @contextmanager
    def tool(
        self,
        name: str,
        *,
        arguments: object = None,
        tool_call_id: str | None = None,
        tool_type: str | None = None,
        tool_description: str | None = None,
    ) -> Iterator[ToolInvocation]:
        """Context manager for Tool invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        invocation = self.start_tool(
            name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            tool_type=tool_type,
            tool_description=tool_description,
        )
        try:
            yield invocation
        except Exception as exc:
            invocation.fail(exc)
            raise
        invocation.stop()

    @contextmanager
    def workflow(
        self,
        name: str | None = None,
    ) -> Iterator[WorkflowInvocation]:
        """Context manager for Workflow invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        invocation = self.start_workflow(name=name)

        try:
            yield invocation
        except Exception as exc:
            invocation.fail(exc)
            raise
        invocation.stop()


def get_telemetry_handler(
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
    logger_provider: LoggerProvider | None = None,
) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: TelemetryHandler | None = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
        )
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
