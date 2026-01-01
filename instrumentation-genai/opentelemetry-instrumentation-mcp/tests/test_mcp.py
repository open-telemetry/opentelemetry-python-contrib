# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for MCP instrumentation."""

import pytest


pytestmark = pytest.mark.asyncio


async def test_mcp_instrumentor(span_exporter, tracer_provider) -> None:
    """Test MCP instrumentation with FastMCP server and client."""
    try:
        from mcp import FastMCP, Client
    except ImportError:
        pytest.skip("mcp package not available")
        return

    # Create a simple MCP server
    server = FastMCP("test-server")

    @server.tool()
    async def add_numbers(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b

    @server.resource("test://greeting")
    def get_greeting() -> str:
        """Get a test greeting."""
        return "Hello from MCP!"

    # Use in-memory client to connect to the server
    async with Client(server) as client:
        # Test tool listing
        tools_res = await client.list_tools()
        assert len(tools_res) >= 1

        # Test tool calling
        result = await client.call_tool("add_numbers", {"a": 5, "b": 3})
        assert len(result.content) >= 1

        # Test resource listing
        resources_res = await client.list_resources()
        assert len(resources_res) >= 1

        # Test resource reading
        resource_result = await client.read_resource("test://greeting")
        assert len(resource_result) >= 1

    # Get the finished spans
    spans = span_exporter.get_finished_spans()

    # Verify spans were created
    assert len(spans) > 0, "No spans were captured"

    # Verify all spans belong to the same trace
    trace_ids = set(span.get_span_context().trace_id for span in spans)
    assert len(trace_ids) == 1, (
        f"Expected all spans in same trace, found {len(trace_ids)} different traces"
    )


async def test_mcp_tool_call(span_exporter, tracer_provider) -> None:
    """Test MCP tool call instrumentation."""
    try:
        from mcp import FastMCP, Client
    except ImportError:
        pytest.skip("mcp package not available")
        return

    server = FastMCP("tool-test-server")

    @server.tool()
    async def multiply(x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    async with Client(server) as client:
        result = await client.call_tool("multiply", {"x": 7, "y": 6})
        assert result.content[0].text == "42"

    spans = span_exporter.get_finished_spans()
    tool_spans = [s for s in spans if "multiply" in s.name or "tool" in s.name.lower()]

    assert len(tool_spans) > 0, "Expected tool call spans"


async def test_mcp_resource_read(span_exporter, tracer_provider) -> None:
    """Test MCP resource read instrumentation."""
    try:
        from mcp import FastMCP, Client
    except ImportError:
        pytest.skip("mcp package not available")
        return

    server = FastMCP("resource-test-server")

    @server.resource("test://data")
    def get_data() -> str:
        """Get test data."""
        return "Test data content"

    async with Client(server) as client:
        result = await client.read_resource("test://data")
        assert result[0].text == "Test data content"

    spans = span_exporter.get_finished_spans()
    resource_spans = [s for s in spans if "resource" in s.name.lower() or "read" in s.name.lower()]

    assert len(resource_spans) > 0, "Expected resource read spans"
