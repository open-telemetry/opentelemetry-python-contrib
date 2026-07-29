# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.context import Context
from opentelemetry.semconv._incubating.attributes import (
    mcp_attributes as MCP,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder


class MCPInvocation(GenAIInvocation):
    """Represents a Model Context Protocol request or notification."""

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        completion_hook: CompletionHook,
        method_name: str,
        *,
        protocol_version: str | None = None,
        session_id: str | None = None,
        resource_uri: str | None = None,
        parent_context: Context | None = None,
    ) -> None:
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            completion_hook,
            operation_name=method_name,
            span_name=method_name,
            span_kind=SpanKind.CLIENT,
        )
        self.method_name = method_name
        self.protocol_version = protocol_version
        self.session_id = session_id
        self.resource_uri = resource_uri
        self._start(
            self._get_attributes(),
            context=parent_context,
        )

    def _get_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (MCP.MCP_PROTOCOL_VERSION, self.protocol_version),
            (MCP.MCP_SESSION_ID, self.session_id),
            (MCP.MCP_RESOURCE_URI, self.resource_uri),
        )
        return {
            MCP.MCP_METHOD_NAME: self.method_name,
            **{
                key: value
                for key, value in optional_attrs
                if value is not None
            },
        }

    def _apply_finish(self, error: Error | None = None) -> None:
        if error is not None:
            self._apply_error_attributes(error)
        attributes = self._get_attributes()
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
