#!/usr/bin/env python3
"""Zero-code instrumentation example for Claude Agent SDK with auto-instrumentation."""

import asyncio
import os
from dotenv import load_dotenv
from claude_agent_sdk import query, ClaudeAgentOptions
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

# Load environment variables
load_dotenv()


async def main():
    """Simple Claude Agent query - instrumentation applied automatically via opentelemetry-instrument."""
    print("=== Zero-Code Example with Auto-Instrumentation ===")
    
    options = ClaudeAgentOptions(
        model=os.getenv("CLAUDE_MODEL", "qwen-plus"),
        max_turns=2
    )
    
    async for message in query(
        prompt="What are the benefits of cloud computing?",
        options=options
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage) and message.total_cost_usd > 0:
            print(f"\nCost: ${message.total_cost_usd:.4f}")
    print()


if __name__ == "__main__":
    asyncio.run(main())