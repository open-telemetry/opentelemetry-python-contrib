#!/usr/bin/env python3
"""Manual instrumentation example for Claude Agent SDK with full OpenTelemetry setup."""

import asyncio
import os

from claude_agent_sdk import query, ClaudeAgentOptions

# NOTE: OpenTelemetry Python Logs API is in beta
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# Configure logging
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)

# Configure metrics
metrics.set_meter_provider(
    MeterProvider(
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
            ),
        ]
    )
)

# Instrument Claude Agent SDK
ClaudeAgentSDKInstrumentor().instrument()

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

async def basic_example():
    """Simple Claude Agent query with tracing."""
    print("=== Basic Example ===")
    
    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for message in query(prompt="What is 2 + 2?", options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
    print()


async def tool_example():
    """Example using tools with Claude Agent."""
    print("\n=== Tool Example ===")

    options = ClaudeAgentOptions(
        model="qwen-plus",
        allowed_tools=["Read", "Write"],
        system_prompt="You are a helpful file assistant.",
    )

    async for message in query(
        prompt="List files in current directory",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage) and message.total_cost_usd > 0:
            print(f"\nCost: ${message.total_cost_usd:.4f}")
    print()


async def main():
    """Run all examples with OpenTelemetry instrumentation."""
    print("Starting Claude Agent SDK with full OpenTelemetry setup...")
    
    await basic_example()
    await tool_example()
    
    print("\n✓ Examples completed. Check your OTLP collector for telemetry data!")


if __name__ == "__main__":
    asyncio.run(main())