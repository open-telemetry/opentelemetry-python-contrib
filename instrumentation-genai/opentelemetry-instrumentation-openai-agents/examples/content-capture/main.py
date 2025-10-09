# pylint: skip-file
"""Content capture OpenAI Agents instrumentation example."""

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
    """Configure the OpenTelemetry SDK and enable event-only capture."""

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


@function_tool
def lookup_weather(city: str) -> str:
    """Return a canned weather response for the requested city."""

    return f"The weather in {city} is mild with occasional sunshine."


def run_agent() -> None:
    """Create a story-driven packing advisor and execute one run."""

    storyteller = Agent(
        name="Packing Coach",
        instructions=(
            "Guide the traveler with tailored packing advice. Use the weather"
            " tool for localized details and describe why each item matters."
        ),
        tools=[lookup_weather],
    )

    result = Runner.run_sync(
        storyteller,
        "I'm headed to Tokyo in the spring. Help me decide what to pack.",
    )

    print("Agent response:")
    print(result.final_output)


def main() -> None:
    load_dotenv()
    configure_tracing()
    run_agent()


if __name__ == "__main__":
    main()
