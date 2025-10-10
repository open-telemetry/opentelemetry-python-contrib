# pylint: skip-file
"""Multi-agent OpenAI Agents instrumentation example."""

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
    """Configure tracing with the default content capture settings."""

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


@function_tool
def lookup_weather(city: str) -> str:
    """Return a canned weekend forecast for the requested city."""

    return f"Expect pleasant spring weather in {city} with cool evenings."


@function_tool
def find_dining(city: str) -> str:
    """Return a canned dining suggestion for the requested city."""

    return (
        f"Reserve a table at a neighborhood izakaya in {city} for fresh seafood"
        " and seasonal specials."
    )


def run_team() -> None:
    """Coordinate two agents and show their combined guidance."""

    travel_planner = Agent(
        name="Travel Planner",
        instructions=(
            "Design a short itinerary with highlights and a quick travel tip."
        ),
        tools=[lookup_weather],
    )

    dining_expert = Agent(
        name="Dining Expert",
        instructions=(
            "Recommend a memorable dining experience that complements the"
            " travel plan provided."
        ),
        tools=[find_dining],
    )

    traveler_question = "I'm visiting Kyoto for a long weekend. Any advice?"

    itinerary = Runner.run_sync(travel_planner, traveler_question)
    dining = Runner.run_sync(
        dining_expert,
        f"Given this plan: {itinerary.final_output}\nSuggest food options.",
    )

    print("Travel planner response:")
    print(itinerary.final_output)
    print("\nDining expert response:")
    print(dining.final_output)


def main() -> None:
    load_dotenv()
    configure_tracing()
    run_team()


if __name__ == "__main__":
    main()
