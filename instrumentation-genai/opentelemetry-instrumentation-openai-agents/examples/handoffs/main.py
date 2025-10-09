# pylint: skip-file
"""Multi-agent handoff example instrumented with OpenTelemetry."""

from __future__ import annotations

import asyncio
import json
import random

from agents import Agent, HandoffInputData, Runner, function_tool, handoff
from agents import trace as agent_trace
from agents.extensions import handoff_filters
from agents.models import is_gpt_5_default
from dotenv import load_dotenv

from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_otel() -> None:
    """Configure the OpenTelemetry SDK and enable the Agents instrumentation."""

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    otel_trace.set_tracer_provider(provider)

    OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


@function_tool
def random_number_tool(maximum: int) -> int:
    """Return a random integer between 0 and ``maximum``."""

    return random.randint(0, maximum)


def spanish_handoff_message_filter(
    handoff_message_data: HandoffInputData,
) -> HandoffInputData:
    """Trim the message history forwarded to the Spanish-speaking agent."""

    if is_gpt_5_default():
        # When GPT-5 is enabled we skip additional filtering.
        return HandoffInputData(
            input_history=handoff_message_data.input_history,
            pre_handoff_items=tuple(handoff_message_data.pre_handoff_items),
            new_items=tuple(handoff_message_data.new_items),
        )

    filtered = handoff_filters.remove_all_tools(handoff_message_data)
    history = (
        tuple(filtered.input_history[2:])
        if isinstance(filtered.input_history, tuple)
        else filtered.input_history[2:]
    )

    return HandoffInputData(
        input_history=history,
        pre_handoff_items=tuple(filtered.pre_handoff_items),
        new_items=tuple(filtered.new_items),
    )


assistant = Agent(
    name="Assistant",
    instructions="Be extremely concise.",
    tools=[random_number_tool],
)

spanish_assistant = Agent(
    name="Spanish Assistant",
    instructions="You only speak Spanish and are extremely concise.",
    handoff_description="A Spanish-speaking assistant.",
)

concierge = Agent(
    name="Concierge",
    instructions=(
        "Be a helpful assistant. If the traveler switches to Spanish, handoff to"
        " the Spanish specialist. Use the random number tool when asked for"
        " numbers."
    ),
    handoffs=[
        handoff(spanish_assistant, input_filter=spanish_handoff_message_filter)
    ],
)


async def run_workflow() -> None:
    """Execute a conversation that triggers tool calls and handoffs."""

    with agent_trace(workflow_name="Travel concierge handoff"):
        # Step 1: Basic conversation with the initial assistant.
        result = await Runner.run(
            assistant,
            input="I'm planning a trip to Madrid. Can you help?",
        )

        print("Step 1 complete")

        # Step 2: Ask for a random number to exercise the tool span.
        result = await Runner.run(
            assistant,
            input=result.to_input_list()
            + [
                {
                    "content": "Pick a lucky number between 0 and 20",
                    "role": "user",
                }
            ],
        )

        print("Step 2 complete")

        # Step 3: Continue the conversation with the concierge agent.
        result = await Runner.run(
            concierge,
            input=result.to_input_list()
            + [
                {
                    "content": "Recommend some sights in Madrid for a weekend trip.",
                    "role": "user",
                }
            ],
        )

        print("Step 3 complete")

        # Step 4: Switch to Spanish to cause a handoff to the specialist.
        result = await Runner.run(
            concierge,
            input=result.to_input_list()
            + [
                {
                    "content": "Por favor habla en español. ¿Puedes resumir el plan?",
                    "role": "user",
                }
            ],
        )

        print("Step 4 complete")

    print("\n=== Conversation Transcript ===\n")
    for message in result.to_input_list():
        print(json.dumps(message, indent=2, ensure_ascii=False))


def main() -> None:
    load_dotenv()
    configure_otel()
    asyncio.run(run_workflow())


if __name__ == "__main__":
    main()
