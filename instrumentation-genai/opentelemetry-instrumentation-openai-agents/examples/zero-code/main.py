"""Zero-code OpenAI Agents example."""

from __future__ import annotations

from agents import Agent, Runner, function_tool


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
    run_agent()


if __name__ == "__main__":
    main()
