# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    mcp_attributes as MCP,
)
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import (
    GenAIInvocation,
    MCPInvocation,
)


def test_mcp_invocation_uses_mcp_semantic_conventions() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    handler = TelemetryHandler(tracer_provider=provider)

    invocation = handler.start_mcp(
        MCP.McpMethodNameValues.TOOLS_LIST.value,
        protocol_version="2025-06-18",
        session_id="session-1",
    )
    assert isinstance(invocation, MCPInvocation)
    assert isinstance(invocation, GenAIInvocation)
    invocation.stop()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == MCP.McpMethodNameValues.TOOLS_LIST.value
    assert span.kind is SpanKind.CLIENT
    assert span.attributes == {
        MCP.MCP_METHOD_NAME: MCP.McpMethodNameValues.TOOLS_LIST.value,
        MCP.MCP_PROTOCOL_VERSION: "2025-06-18",
        MCP.MCP_SESSION_ID: "session-1",
    }
