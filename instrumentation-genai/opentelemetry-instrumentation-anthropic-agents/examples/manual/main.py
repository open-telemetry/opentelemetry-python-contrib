# pylint: skip-file
"""Example of instrumenting Claude Agent SDK with manual OpenTelemetry setup.

Based on https://github.com/anthropics/claude-agent-sdk-python/blob/main/examples/agents.py

This example defines a code reviewer agent and a documentation writer agent,
then runs queries against them while exporting traces, logs, and metrics to
an OTLP compatible endpoint.
"""

import anyio
from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
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
from opentelemetry.instrumentation.anthropic_agents import (
    AnthropicAgentsInstrumentor,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)

# configure metrics
metrics.set_meter_provider(
    MeterProvider(
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
            ),
        ]
    )
)

# instrument Claude Agent SDK
AnthropicAgentsInstrumentor().instrument()


async def code_reviewer_example():
    """Run a code reviewer agent that analyzes code for best practices."""
    print("=== Code Reviewer Agent Example ===")

    options = ClaudeAgentOptions(
        agents={
            "code-reviewer": AgentDefinition(
                description="Reviews code for best practices and potential issues",
                prompt=(
                    "You are a code reviewer. Analyze code for bugs, "
                    "performance issues, security vulnerabilities, and "
                    "adherence to best practices. Provide constructive feedback."
                ),
                tools=["Read", "Grep"],
                model="sonnet",
            ),
        },
    )

    async for message in query(
        prompt="Use the code-reviewer agent to review the code in this file",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif (
            isinstance(message, ResultMessage)
            and message.total_cost_usd
            and message.total_cost_usd > 0
        ):
            print(f"\nCost: ${message.total_cost_usd:.4f}")
    print()


async def documentation_writer_example():
    """Run a documentation writer agent."""
    print("=== Documentation Writer Agent Example ===")

    options = ClaudeAgentOptions(
        agents={
            "doc-writer": AgentDefinition(
                description="Writes comprehensive documentation",
                prompt=(
                    "You are a technical documentation expert. Write clear, "
                    "comprehensive documentation with examples. Focus on "
                    "clarity and completeness."
                ),
                tools=["Read", "Write", "Edit"],
                model="sonnet",
            ),
        },
    )

    async for message in query(
        prompt="Use the doc-writer agent to explain what AgentDefinition is used for",
        options=options,
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif (
            isinstance(message, ResultMessage)
            and message.total_cost_usd
            and message.total_cost_usd > 0
        ):
            print(f"\nCost: ${message.total_cost_usd:.4f}")
    print()


async def main():
    """Run all agent examples."""
    await code_reviewer_example()
    await documentation_writer_example()


if __name__ == "__main__":
    anyio.run(main)
