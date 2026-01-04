"""
Content capture demo for the OpenAI Agents instrumentation.

This script spins up the instrumentation with message capture enabled and
simulates an agent invocation plus a tool call using the tracing helpers from
the ``openai-agents`` package. Spans are exported to the console so you can
inspect captured prompts, responses, and tool payloads without making any
OpenAI API calls.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agents.tracing import agent_span, function_span, generation_span, trace
from dotenv import load_dotenv

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

load_dotenv()  # take environment variables from .env.


def configure_tracing() -> None:
    """Configure a tracer provider that exports spans via OTLP."""
    resource = Resource.create(
        {
            "service.name": os.environ.get(
                "OTEL_SERVICE_NAME", "openai-agents-content-capture-demo"
            )
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    # Instrument with explicit content capture mode to ensure prompts/responses are recorded.
    OpenAIAgentsInstrumentor().instrument(
        tracer_provider=provider,
        capture_message_content="span_and_event",
        system="openai",
        agent_name="Travel Concierge",
        base_url="https://api.openai.com/v1",
    )


def dump(title: str, payload: Any) -> None:
    """Pretty-print helper used to show intermediate context."""
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2))


def run_workflow() -> None:
    """Simulate an agent workflow with a generation and a tool invocation."""
    itinerary_prompt = [
        {"role": "system", "content": "Plan high level travel itineraries."},
        {
            "role": "user",
            "content": "I'm visiting Paris for 3 days in November.",
        },
    ]

    tool_args = {"city": "Paris", "date": "2025-11-12"}
    tool_result = {
        "forecast": "Mostly sunny, highs 15°C",
        "packing_tips": ["light jacket", "comfortable shoes"],
    }

    with trace("travel-booking-workflow"):
        with agent_span(name="travel_planner") as agent:
            dump(
                "Agent span started",
                {"span_id": agent.span_id, "trace_id": agent.trace_id},
            )

            with generation_span(
                input=itinerary_prompt,
                output=[
                    {
                        "role": "assistant",
                        "content": (
                            "Day 1 visit the Louvre, Day 2 tour Versailles, "
                            "Day 3 explore Montmartre."
                        ),
                    }
                ],
                model="gpt-4o-mini",
                usage={
                    "input_tokens": 128,
                    "output_tokens": 96,
                    "total_tokens": 224,
                },
            ):
                pass

            with function_span(
                name="fetch_weather",
                input=json.dumps(tool_args),
                output=tool_result,
            ):
                pass

    print(
        "\nWorkflow complete – spans exported to the configured OTLP endpoint."
    )


def main() -> None:
    configure_tracing()
    run_workflow()


if __name__ == "__main__":
    main()
