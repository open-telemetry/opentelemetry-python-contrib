# pylint: skip-file
"""Example of instrumenting Claude Agent SDK with zero-code OpenTelemetry.

Based on https://github.com/anthropics/claude-agent-sdk-python/blob/main/examples/agents.py

This example defines a code reviewer agent and a documentation writer agent,
then runs queries against them. Instrumentation is handled automatically by
the ``opentelemetry-instrument`` CLI — no OpenTelemetry setup code needed.
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
