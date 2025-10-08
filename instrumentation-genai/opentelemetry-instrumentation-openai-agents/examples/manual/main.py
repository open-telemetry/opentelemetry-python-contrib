# pylint: skip-file
"""Manual OpenAI Agents instrumentation example."""

from __future__ import annotations

from agents import Agent, Runner, function_tool

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_otel() -> None:
    """Configure the OpenTelemetry SDK for exporting spans."""

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


@function_tool
def get_weather(city: str) -> str:
    """Return a canned weather response for the requested city."""

    return f"The forecast for {city} is sunny with pleasant temperatures."


def run_agent() -> None:
    """Create a simple agent and execute a single run."""

    assistant = Agent(
        name="Travel Concierge",
        instructions=(
            "You are a concise travel concierge. Use the weather tool when the"
            " traveler asks about local conditions."
        ),
        tools=[get_weather],
    )

    result = Runner.run_sync(
        assistant,
        "I'm visiting Barcelona this weekend. How should I pack?",
    )

    print("Agent response:")
    print(result.final_output)


def main() -> None:
    configure_otel()
    run_agent()


if __name__ == "__main__":
    main()
