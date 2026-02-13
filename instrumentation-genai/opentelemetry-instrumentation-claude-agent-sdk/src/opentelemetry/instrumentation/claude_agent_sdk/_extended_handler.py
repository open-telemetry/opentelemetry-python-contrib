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
Extended telemetry handler for Claude Agent SDK instrumentation.

This module provides extended telemetry handling specifically for Claude Agent SDK
operations including tool execution and agent invocation tracking.
"""

import timeit
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import context as otel_context
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as GenAI
from opentelemetry.trace import Span, SpanKind, StatusCode, set_span_in_context
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

from ._extended_types import ExecuteToolInvocation, InvokeAgentInvocation


def _apply_execute_tool_finish_attributes(span: Span, invocation: ExecuteToolInvocation) -> None:
    """Apply finish attributes for tool execution spans."""
    # Set operation name first
    span.set_attribute(GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value)
    
    # Set tool name
    if invocation.tool_name:
        span.set_attribute(GenAI.GEN_AI_TOOL_NAME, invocation.tool_name)
    
    if invocation.provider:
        span.set_attribute(GenAI.GEN_AI_PROVIDER_NAME, invocation.provider)
    
    if invocation.tool_call_id:
        span.set_attribute("gen_ai.tool.call.id", invocation.tool_call_id)
    
    if invocation.tool_description:
        span.set_attribute("gen_ai.tool.description", invocation.tool_description)
    
    if invocation.tool_type:
        span.set_attribute("gen_ai.tool.type", invocation.tool_type)
    
    if invocation.tool_call_arguments is not None:
        span.set_attribute("gen_ai.tool.input", str(invocation.tool_call_arguments))
    
    if invocation.tool_call_result is not None:
        span.set_attribute("gen_ai.tool.result", str(invocation.tool_call_result))


def _apply_invoke_agent_finish_attributes(span: Span, invocation: InvokeAgentInvocation) -> None:
    """Apply finish attributes for agent invocation spans."""
    # Set operation name first
    span.set_attribute(GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.INVOKE_AGENT.value)
    
    if invocation.provider:
        span.set_attribute(GenAI.GEN_AI_PROVIDER_NAME, invocation.provider)
    
    if invocation.agent_name:
        span.set_attribute("gen_ai.agent.name", invocation.agent_name)
    
    if invocation.agent_id:
        span.set_attribute("gen_ai.agent.id", invocation.agent_id)
    
    if invocation.agent_description:
        span.set_attribute("gen_ai.agent.description", invocation.agent_description)
    
    if invocation.conversation_id:
        span.set_attribute("gen_ai.conversation.id", invocation.conversation_id)
    
    if invocation.request_model:
        span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model)
    
    if invocation.response_model_name:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_MODEL, invocation.response_model_name)
    
    if invocation.response_id:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, invocation.response_id)
    
    if invocation.input_tokens is not None:
        span.set_attribute(GenAI.GEN_AI_USAGE_INPUT_TOKENS, invocation.input_tokens)
    
    if invocation.output_tokens is not None:
        span.set_attribute(GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, invocation.output_tokens)
    
    if invocation.finish_reasons:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_FINISH_REASONS, invocation.finish_reasons)


def _apply_error_attributes(span: Span, error: Error) -> None:
    """Apply error attributes to a span."""
    span.set_status(StatusCode.ERROR, error.message)
    span.set_attribute("error.type", error.type.__name__)
    span.set_attribute("error.message", error.message)


class ExtendedTelemetryHandlerForClaude:
    """
    Extended Telemetry Handler specifically for Claude Agent SDK.
    
    This class provides the extended functionality needed for Claude Agent SDK
    instrumentation without depending on the external extended_handler module.
    """

    def __init__(self, base_handler: TelemetryHandler):
        self._base_handler = base_handler
        self._tracer = base_handler._tracer

    def start_execute_tool(
        self, invocation: ExecuteToolInvocation
    ) -> ExecuteToolInvocation:
        """Start a tool execution invocation and create a pending span entry."""
        span = self._tracer.start_span(
            name=f"{GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value} {invocation.tool_name}",
            kind=SpanKind.INTERNAL,
        )
        # Record a monotonic start timestamp (seconds) for duration
        # calculation using timeit.default_timer.
        invocation.monotonic_start_s = timeit.default_timer()
        invocation.span = span
        invocation.context_token = otel_context.attach(
            set_span_in_context(span)
        )
        return invocation

    def stop_execute_tool(
        self, invocation: ExecuteToolInvocation
    ) -> ExecuteToolInvocation:
        """Finalize a tool execution invocation successfully and end its span."""
        if invocation.context_token is None or invocation.span is None:
            return invocation

        _apply_execute_tool_finish_attributes(invocation.span, invocation)
        otel_context.detach(invocation.context_token)
        invocation.span.end()
        return invocation

    def fail_execute_tool(
        self, invocation: ExecuteToolInvocation, error: Error
    ) -> ExecuteToolInvocation:
        """Fail a tool execution invocation and end its span with error status."""
        if invocation.context_token is None or invocation.span is None:
            return invocation

        _apply_execute_tool_finish_attributes(invocation.span, invocation)
        _apply_error_attributes(invocation.span, error)
        otel_context.detach(invocation.context_token)
        invocation.span.end()
        return invocation

    @contextmanager
    def execute_tool(
        self, invocation: ExecuteToolInvocation | None = None
    ) -> Iterator[ExecuteToolInvocation]:
        """Context manager for tool execution invocations."""
        if invocation is None:
            invocation = ExecuteToolInvocation(tool_name="")
        self.start_execute_tool(invocation)
        try:
            yield invocation
        except Exception as exc:
            self.fail_execute_tool(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise
        self.stop_execute_tool(invocation)

    def start_invoke_agent(
        self, invocation: InvokeAgentInvocation
    ) -> InvokeAgentInvocation:
        """Start an agent invocation and create a pending span entry."""
        if invocation.agent_name:
            span_name = f"{GenAI.GenAiOperationNameValues.INVOKE_AGENT.value} {invocation.agent_name}"
        else:
            span_name = GenAI.GenAiOperationNameValues.INVOKE_AGENT.value

        # Span kind should be INTERNAL for in-process agents, CLIENT for remote services
        # Default to INTERNAL as most frameworks run agents in-process
        span = self._tracer.start_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
        )
        # Record a monotonic start timestamp (seconds) for duration
        # calculation using timeit.default_timer.
        invocation.monotonic_start_s = timeit.default_timer()
        invocation.span = span
        invocation.context_token = otel_context.attach(
            set_span_in_context(span)
        )
        return invocation

    def stop_invoke_agent(
        self, invocation: InvokeAgentInvocation
    ) -> InvokeAgentInvocation:
        """Finalize an agent invocation successfully and end its span."""
        if invocation.context_token is None or invocation.span is None:
            return invocation

        _apply_invoke_agent_finish_attributes(invocation.span, invocation)
        otel_context.detach(invocation.context_token)
        invocation.span.end()
        return invocation

    def fail_invoke_agent(
        self, invocation: InvokeAgentInvocation, error: Error
    ) -> InvokeAgentInvocation:
        """Fail an agent invocation and end its span with error status."""
        if invocation.context_token is None or invocation.span is None:
            return invocation

        span = invocation.span
        _apply_invoke_agent_finish_attributes(span, invocation)
        _apply_error_attributes(span, error)
        otel_context.detach(invocation.context_token)
        span.end()
        return invocation

    @contextmanager
    def invoke_agent(
        self, invocation: InvokeAgentInvocation | None = None
    ) -> Iterator[InvokeAgentInvocation]:
        """Context manager for agent invocations."""
        if invocation is None:
            invocation = InvokeAgentInvocation(provider="")
        self.start_invoke_agent(invocation)
        try:
            yield invocation
        except Exception as exc:
            self.fail_invoke_agent(
                invocation, Error(message=str(exc), type=type(exc))
            )
            raise
        self.stop_invoke_agent(invocation)

    # Delegate LLM methods to base handler
    def start_llm(self, *args, **kwargs):
        return self._base_handler.start_llm(*args, **kwargs)
    
    def stop_llm(self, *args, **kwargs):
        return self._base_handler.stop_llm(*args, **kwargs)
    
    def fail_llm(self, *args, **kwargs):
        return self._base_handler.fail_llm(*args, **kwargs)
    
    @contextmanager
    def llm(self, *args, **kwargs):
        with self._base_handler.llm(*args, **kwargs) as invocation:
            yield invocation