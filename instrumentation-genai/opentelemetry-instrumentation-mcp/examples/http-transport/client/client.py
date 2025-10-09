#!/usr/bin/env python3
"""MCP client with HTTP transport using SSE."""

import asyncio

from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import AnyUrl

from opentelemetry import trace


async def main():
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("mcp_http_client"):
        # Connect to MCP server via HTTP
        async with sse_client("http://localhost:8000/sse") as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize
                await session.initialize()

                # List tools
                tools = await session.list_tools()
                print(f"Available tools: {[t.name for t in tools.tools]}")

                # Call pingweb tool
                result = await session.call_tool(
                    "pingweb", arguments={"url": "http://www.aws.com"}
                )
                print(f"pingweb result: {result.content}")

                # Call awssdkcall tool
                result = await session.call_tool("awssdkcall")
                print(f"awssdkcall result: {result.content}")

                # Call tool
                result = await session.call_tool(
                    "add", arguments={"a": 5, "b": 3}
                )
                print(f"add(5, 3) = {result.content}")

                # Read resource
                greeting = await session.read_resource(
                    AnyUrl("greeting://World")
                )
                print(f"Greeting: {greeting}")


if __name__ == "__main__":
    asyncio.run(main())
