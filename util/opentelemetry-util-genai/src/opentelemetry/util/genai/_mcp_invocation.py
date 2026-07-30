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
    """Represent an MCP client operation.

    Follows the `MCP client semantic conventions
    <https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md#client>`_.
    ``mcp.method.name`` is always set. ``mcp.protocol.version`` is set only
    when ``protocol_version`` is provided, and ``mcp.session.id`` is set only
    when ``session_id`` is provided.
    """

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
        self._start(
            self._get_attributes(),
            context=parent_context,
        )

    def _get_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (MCP.MCP_PROTOCOL_VERSION, self.protocol_version),
            (MCP.MCP_SESSION_ID, self.session_id),
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
