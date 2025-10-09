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

"""Tests for attribute constants."""

import unittest

from opentelemetry.instrumentation.mcp.attributes import (
    MCPMethodValue,
    MCPSpanAttributes,
)


class TestMCPSpanAttributes(unittest.TestCase):
    """Test MCPSpanAttributes constants."""

    def test_mcp_method_name(self):
        """Test MCP_METHOD_NAME constant."""
        self.assertEqual(MCPSpanAttributes.MCP_METHOD_NAME, "mcp.method.name")

    def test_mcp_request_id(self):
        """Test MCP_REQUEST_ID constant."""
        self.assertEqual(MCPSpanAttributes.MCP_REQUEST_ID, "mcp.request.id")

    def test_mcp_tool_name(self):
        """Test MCP_TOOL_NAME constant."""
        self.assertEqual(MCPSpanAttributes.MCP_TOOL_NAME, "mcp.tool.name")

    def test_mcp_request_argument(self):
        """Test MCP_REQUEST_ARGUMENT constant."""
        self.assertEqual(
            MCPSpanAttributes.MCP_REQUEST_ARGUMENT, "mcp.request.argument"
        )

    def test_mcp_prompt_name(self):
        """Test MCP_PROMPT_NAME constant."""
        self.assertEqual(MCPSpanAttributes.MCP_PROMPT_NAME, "mcp.prompt.name")

    def test_mcp_resource_uri(self):
        """Test MCP_RESOURCE_URI constant."""
        self.assertEqual(
            MCPSpanAttributes.MCP_RESOURCE_URI, "mcp.resource.uri"
        )

    def test_mcp_transport_type(self):
        """Test MCP_TRANSPORT_TYPE constant."""
        self.assertEqual(
            MCPSpanAttributes.MCP_TRANSPORT_TYPE, "mcp.transport.type"
        )

    def test_mcp_session_id(self):
        """Test MCP_SESSION_ID constant."""
        self.assertEqual(MCPSpanAttributes.MCP_SESSION_ID, "mcp.session.id")


class TestMCPMethodValue(unittest.TestCase):
    """Test MCPMethodValue constants."""

    def test_notifications_cancelled(self):
        """Test NOTIFICATIONS_CANCELLED constant."""
        self.assertEqual(
            MCPMethodValue.NOTIFICATIONS_CANCELLED, "notifications/cancelled"
        )

    def test_notifications_initialized(self):
        """Test NOTIFICATIONS_INITIALIZED constant."""
        self.assertEqual(
            MCPMethodValue.NOTIFICATIONS_INITIALIZED,
            "notifications/initialized",
        )

    def test_notifications_progress(self):
        """Test NOTIFICATIONS_PROGRESS constant."""
        self.assertEqual(
            MCPMethodValue.NOTIFICATIONS_PROGRESS, "notifications/progress"
        )

    def test_resources_list(self):
        """Test RESOURCES_LIST constant."""
        self.assertEqual(MCPMethodValue.RESOURCES_LIST, "resources/list")

    def test_tools_list(self):
        """Test TOOLS_LIST constant."""
        self.assertEqual(MCPMethodValue.TOOLS_LIST, "tools/list")

    def test_tools_call(self):
        """Test TOOLS_CALL constant."""
        self.assertEqual(MCPMethodValue.TOOLS_CALL, "tools/call")

    def test_initialized(self):
        """Test INITIALIZED constant."""
        self.assertEqual(MCPMethodValue.INITIALIZED, "initialize")

    def test_prompts_get(self):
        """Test PROMPTS_GET constant."""
        self.assertEqual(MCPMethodValue.PROMPTS_GET, "prompts/get")
