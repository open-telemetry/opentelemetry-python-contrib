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

"""
MCP (Model Context Protocol) Semantic Conventions.

Based off of: https://github.com/open-telemetry/semantic-conventions/pull/2083

WARNING: These semantic conventions are currently in development and are considered unstable.
They may change at any time without notice. Use with caution in production environments.
"""


class MCPSpanAttributes:
    MCP_METHOD_NAME = "mcp.method.name"
    """
    The name of the request or notification method.
    Examples: notifications/cancelled; initialize; notifications/initialized
    """
    MCP_REQUEST_ID = "mcp.request.id"
    """
    This is a unique identifier for the request.
    Conditionally Required when the client executes a request.
    """
    MCP_TOOL_NAME = "mcp.tool.name"
    """
    The name of the tool provided in the request.
    Conditionally Required when operation is related to a specific tool.
    """
    MCP_REQUEST_ARGUMENT = "mcp.request.argument"
    """
    Full attribute: mcp.request.argument.<key>
    Additional arguments passed to the request within params object. <key> being the normalized argument name (lowercase), the value being the argument value.
    """
    MCP_PROMPT_NAME = "mcp.prompt.name"
    """
    The name of the prompt or prompt template provided in the request or response
    Conditionally Required when operation is related to a specific prompt.
    """
    MCP_RESOURCE_URI = "mcp.resource.uri"
    """
    The value of the resource uri.
    Conditionally Required when the client executes a request type that includes a resource URI parameter.
    """
    MCP_TRANSPORT_TYPE = "mcp.transport.type"
    """
    The transport type used for MCP communication.
    Examples: stdio, streamable_http
    """
    MCP_SESSION_ID = "mcp.session.id"
    """
    The session identifier for HTTP transport connections.
    Only present for streamable_http transport, not available for stdio.
    """


class MCPMethodValue:
    NOTIFICATIONS_CANCELLED = "notifications/cancelled"
    """
    Notification cancelling a previously-issued request.
    """

    NOTIFICATIONS_INITIALIZED = "notifications/initialized"
    """
    Notification indicating that the MCP client has been initialized.
    """
    NOTIFICATIONS_PROGRESS = "notifications/progress"
    """
    Notification indicating the progress for a long-running operation.
    """
    RESOURCES_LIST = "resources/list"
    """
    Request to list resources available on server.
    """
    TOOLS_LIST = "tools/list"
    """
    Request to list tools available on server.
    """
    TOOLS_CALL = "tools/call"
    """
    Request to call a tool.
    """
    INITIALIZED = "initialize"
    """
    Request to initialize the MCP client.
    """

    PROMPTS_GET = "prompts/get"
    """
    Request to get a prompt.
    """
