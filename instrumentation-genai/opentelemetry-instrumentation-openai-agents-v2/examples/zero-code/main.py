"""Zero-code OpenAI Agents example."""

from __future__ import annotations

from agents import Agent, Runner, function_tool
from dotenv import load_dotenv

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing() -> None:
    """Ensure tracing exports spans even without auto-instrumentation."""

    current_provider = trace.get_tracer_provider()
    if isinstance(current_provider, TracerProvider):
        provider = current_provider
    else:
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

    OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


@function_tool
def get_weather(city: str) -> str:
    """Return a canned weather response for the requested city."""

    return f"The forecast for {city} is sunny with pleasant temperatures."


def run_agent() -> None:
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
    load_dotenv()
    configure_tracing()
    run_agent()


if __name__ == "__main__":
    main()
