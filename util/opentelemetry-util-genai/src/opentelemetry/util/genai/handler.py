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

from contextlib import AbstractContextManager

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
from opentelemetry.util.genai._agent_invocation import AgentInvocation
from opentelemetry.util.genai._inference_invocation import (
    LLMInvocation,
)
from opentelemetry.util.genai._invocation import Error
from opentelemetry.util.genai.invocation import (
    EmbeddingInvocation,
    InferenceInvocation,
    ToolInvocation,
    WorkflowInvocation,
)
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.version import __version__


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

    def start_llm(self, invocation: LLMInvocation) -> LLMInvocation:
        """Start an LLM invocation.

        .. deprecated::
            Use ``handler.start_inference()`` instead.
        """
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

    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:  # pylint: disable=no-self-use
        """Finalize an LLM invocation successfully and end its span.

        .. deprecated::
            Use ``handler.start_inference()``  and then ``inference.stop()`` instead.
        """
        invocation._sync_to_invocation()
        if invocation._inference_invocation is not None:
            invocation._inference_invocation.stop()
        return invocation

    def fail_llm(  # pylint: disable=no-self-use
        self,
        invocation: LLMInvocation,
        error: Error,
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status.

        .. deprecated::
            Use ``handler.start_inference()``  and then ``inference.fail()`` instead.
        """
        invocation._sync_to_invocation()
        if invocation._inference_invocation is not None:
            invocation._inference_invocation.fail(error)
        return invocation

    def inference(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
    ) -> AbstractContextManager[InferenceInvocation]:
        """Context manager for LLM inference invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        return self.start_inference(
            provider=provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
        )._managed()

    def embedding(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
    ) -> AbstractContextManager[EmbeddingInvocation]:
        """Context manager for Embedding invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        return self.start_embedding(
            provider=provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
        )._managed()

    def tool(
        self,
        name: str,
        *,
        arguments: object = None,
        tool_call_id: str | None = None,
        tool_type: str | None = None,
        tool_description: str | None = None,
    ) -> AbstractContextManager[ToolInvocation]:
        """Context manager for Tool invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        return self.start_tool(
            name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            tool_type=tool_type,
            tool_description=tool_description,
        )._managed()

    def start_agent(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        agent_name: str | None = None,
    ) -> AgentInvocation:
        """Create and start an agent invocation.

        Set remaining attributes on the returned invocation, then call
        invocation.stop() or invocation.fail().
        """
        return AgentInvocation(
            self._tracer,
            self._metrics_recorder,
            self._logger,
            provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
            agent_name=agent_name,
        )

    def invoke_agent(
        self,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        agent_name: str | None = None,
    ) -> AbstractContextManager[AgentInvocation]:
        """Context manager for agent invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        return self.start_agent(
            provider,
            request_model=request_model,
            server_address=server_address,
            server_port=server_port,
            agent_name=agent_name,
        )._managed()

    def workflow(
        self,
        name: str | None = None,
    ) -> AbstractContextManager[WorkflowInvocation]:
        """Context manager for Workflow invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        return self.start_workflow(name=name)._managed()


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
