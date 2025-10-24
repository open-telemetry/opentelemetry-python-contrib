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

"""OpenTelemetry MCP (Model Context Protocol) instrumentation."""

import json
import logging
from typing import Any, Callable, Collection, Coroutine, Dict, Optional, Tuple

from wrapt import register_post_import_hook  # type: ignore[import-untyped]

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.propagate import get_global_textmap
from opentelemetry.trace import SpanKind, Status, StatusCode

from .attributes import MCPMethodValue, MCPSpanAttributes
from .version import __version__

_LOG = logging.getLogger(__name__)


class McpInstrumentor(BaseInstrumentor):
    """
    Instrumentor for MCP (Model Context Protocol).

    Provides automatic tracing for MCP client and server operations,
    including distributed trace context propagation.

    See: https://modelcontextprotocol.io/overview
    """

    _CLIENT_SPAN_NAME = "mcp.client"
    _SERVER_SPAN_NAME = "mcp.server"
    _SESSION_ID_HEADER = "mcp-session-id"
    _SESSION_MODULE = "mcp.shared.session"
    _SERVER_MODULE = "mcp.server.lowlevel.server"

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize the MCP instrumentor.

        Args:
            tracer_provider: Optional tracer provider to use
            propagators: Optional propagators for context injection/extraction
        """
        _LOG.info("Initializing MCP instrumentor.")
        super().__init__()
        self.propagators = kwargs.get("propagators") or get_global_textmap()
        self.tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider=kwargs.get("tracer_provider"),
        )

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the dependencies required for this instrumentation."""
        return ("mcp >= 1.8.1",)

    def _instrument(self, **kwargs: Any) -> None:
        """Apply instrumentation to MCP library."""
        _LOG.debug("Instrument MCP client-side session methods.")
        McpInstrumentor._register_hook(
            self._SESSION_MODULE,
            "BaseSession.send_request",
            self._wrap_session_send,
        )
        McpInstrumentor._register_hook(
            self._SESSION_MODULE,
            "BaseSession.send_notification",
            self._wrap_session_send,
        )

        _LOG.debug("Instrument MCP server-side session methods.")
        McpInstrumentor._register_hook(
            self._SERVER_MODULE,
            "Server._handle_request",
            self._wrap_server_handle_request,
        )
        McpInstrumentor._register_hook(
            self._SERVER_MODULE,
            "Server._handle_notification",
            self._wrap_server_handle_notification,
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Remove instrumentation from MCP library."""
        unwrap(self._SESSION_MODULE, "BaseSession.send_request")
        unwrap(self._SESSION_MODULE, "BaseSession.send_notification")
        unwrap(self._SERVER_MODULE, "Server._handle_request")
        unwrap(self._SERVER_MODULE, "Server._handle_notification")

    @staticmethod
    def _register_hook(
        module: str, target: str, wrapper: Callable[..., Any]
    ) -> None:
        """Register a post-import hook for wrapping a function."""
        # pylint: disable=import-outside-toplevel
        from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]

        def hook(_module: Any) -> None:
            wrap_function_wrapper(module, target, wrapper)

        register_post_import_hook(hook, module)

    def _wrap_session_send(
        self,
        wrapped: Callable[..., Coroutine[Any, Any, Any]],
        instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Coroutine[Any, Any, Any]:
        """
        Wrap BaseSession.send_request and send_notification methods.

        Instruments outgoing MCP messages by:
        1. Creating a span for the operation
        2. Injecting trace context into the message
        3. Recording message attributes

        Args:
            wrapped: Original method being wrapped
            instance: BaseSession instance
            args: Positional arguments (message, ...)
            kwargs: Keyword arguments

        Returns:
            Coroutine that executes the wrapped method
        """
        from mcp.types import (  # pylint: disable=import-outside-toplevel
            ClientNotification,
            ClientRequest,
        )

        async def async_wrapper() -> Any:
            message = args[0] if args else None
            if not message:
                return await wrapped(*args, **kwargs)

            # Determine span kind based on message type
            is_client = isinstance(
                message, (ClientRequest, ClientNotification)
            )
            span_name = (
                self._CLIENT_SPAN_NAME if is_client else self._SERVER_SPAN_NAME
            )
            span_kind = SpanKind.CLIENT if is_client else SpanKind.SERVER

            # Serialize message for modification
            try:
                message_json = message.model_dump(
                    by_alias=True, mode="json", exclude_none=True
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOG.warning(
                    "Failed to serialize message for tracing: %s", exc
                )
                return await wrapped(*args, **kwargs)

            # Ensure _meta field exists for trace context
            message_json.setdefault("params", {}).setdefault("_meta", {})

            with self.tracer.start_as_current_span(
                name=span_name, kind=span_kind
            ) as span:
                # Inject trace context
                ctx = trace.set_span_in_context(span)
                carrier: Dict[str, Any] = {}
                self.propagators.inject(carrier=carrier, context=ctx)
                message_json["params"]["_meta"].update(carrier)

                # Set span attributes
                request_id = getattr(instance, "_request_id", None)
                McpInstrumentor._generate_mcp_message_attrs(
                    span, message, request_id
                )

                # Reconstruct message with injected context
                try:
                    modified_message = message.model_validate(message_json)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    _LOG.warning(
                        "Failed to reconstruct message for tracing: %s", exc
                    )
                    return await wrapped(*args, **kwargs)
                new_args = (modified_message,) + args[1:]

                try:
                    result = await wrapped(*new_args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        return async_wrapper()

    async def _wrap_server_handle_request(
        self,
        wrapped: Callable[..., Coroutine[Any, Any, Any]],
        instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        """
        Wrap Server._handle_request method.

        Args:
            wrapped: Original method
            instance: Server instance
            args: (session, request)
            kwargs: Keyword arguments
        """
        # https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/lowlevel/server.py
        incoming_req = args[1] if len(args) > 1 else None
        return await self._wrap_server_message_handler(
            wrapped, instance, args, kwargs, incoming_msg=incoming_req
        )

    async def _wrap_server_handle_notification(
        self,
        wrapped: Callable[..., Coroutine[Any, Any, Any]],
        instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        """
        Wrap Server._handle_notification method.

        Args:
            wrapped: Original method
            instance: Server instance
            args: (notification,)
            kwargs: Keyword arguments
        """
        # https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/lowlevel/server.py
        incoming_notif = args[0] if args else None
        return await self._wrap_server_message_handler(
            wrapped, instance, args, kwargs, incoming_msg=incoming_notif
        )

    async def _wrap_server_message_handler(
        self,
        wrapped: Callable[..., Coroutine[Any, Any, Any]],
        instance: Any,
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        incoming_msg: Optional[Any],
    ) -> Any:
        """
        Common handler for server-side request and notification processing.

        Instruments incoming MCP messages by:
        1. Extracting trace context from the message
        2. Creating a linked server span
        3. Recording message attributes

        Args:
            wrapped: Original method
            instance: Server instance
            args: Method arguments
            kwargs: Keyword arguments
            incoming_msg: The incoming request or notification

        Returns:
            Result from the wrapped method
        """
        if not incoming_msg:
            return await wrapped(*args, **kwargs)

        # Extract request ID if present (only in requests, not notifications)
        request_id = getattr(incoming_msg, "id", None)

        # Extract trace context from message metadata
        carrier = self._extract_trace_context(incoming_msg)
        parent_ctx = self.propagators.extract(carrier=carrier)

        with self.tracer.start_as_current_span(
            self._SERVER_SPAN_NAME,
            kind=SpanKind.SERVER,
            context=parent_ctx,
        ) as span:
            # Add session ID if available (HTTP transport)
            session_id = self._extract_session_id(args)
            if session_id:
                span.set_attribute(
                    MCPSpanAttributes.MCP_SESSION_ID, session_id
                )

            # Set message-specific attributes
            McpInstrumentor._generate_mcp_message_attrs(
                span, incoming_msg, request_id
            )

            try:
                result = await wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise

    def _extract_trace_context(self, message: Any) -> Dict[str, Any]:  # pylint: disable=no-self-use
        """
        Extract trace context carrier from message metadata.

        Args:
            message: Incoming MCP message

        Returns:
            Dictionary containing trace context or empty dict
        """
        try:
            if (
                hasattr(message, "params")
                and hasattr(message.params, "meta")
                and message.params.meta
            ):
                return message.params.meta.model_dump()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOG.debug("Failed to extract trace context: %s", exc)
        return {}

    def _extract_session_id(self, args: Tuple[Any, ...]) -> Optional[str]:  # pylint: disable=no-self-use
        """
        Extract session ID from HTTP transport headers.

        Args:
            args: Server method arguments

        Returns:
            Session ID if available, None otherwise
        """
        try:
            # pylint: disable=import-outside-toplevel
            from mcp.shared.message import ServerMessageMetadata
            from mcp.shared.session import RequestResponder

            if not args:
                return None

            message = args[0]
            if not isinstance(message, RequestResponder):
                return None

            metadata = message.message_metadata
            if not isinstance(metadata, ServerMessageMetadata):
                return None

            request_context = metadata.request_context
            if not request_context:
                return None

            headers = getattr(request_context, "headers", None)
            if headers:
                return headers.get(self._SESSION_ID_HEADER)

        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOG.debug("Failed to extract session ID: %s", exc)

        return None

    @staticmethod
    def _generate_mcp_message_attrs(
        span: trace.Span, message: Any, request_id: Optional[int]
    ) -> None:
        """
        Populate span with MCP semantic convention attributes.

        Based on: https://github.com/open-telemetry/semantic-conventions/pull/2083
        Note: These conventions are currently unstable and may change.

        Args:
            span: Span to enrich with attributes
            message: MCP message (ClientRequest, ServerRequest, etc.)
            request_id: Request ID if available (None for notifications)
        """
        from mcp import types  # pylint: disable=import-outside-toplevel

        # Unwrap root if present (client-side messages)
        if hasattr(message, "root"):
            message = message.root

        # Set request ID if present
        if request_id is not None:
            span.set_attribute(MCPSpanAttributes.MCP_REQUEST_ID, request_id)

        # Always set method name
        span.set_attribute(MCPSpanAttributes.MCP_METHOD_NAME, message.method)

        # Set message-type-specific attributes
        if isinstance(message, types.CallToolRequest):
            tool_name = message.params.name
            span.update_name(f"{MCPMethodValue.TOOLS_CALL} {tool_name}")
            span.set_attribute(MCPSpanAttributes.MCP_TOOL_NAME, tool_name)

            # Add tool arguments as attributes
            if message.params.arguments:
                for arg_name, arg_val in message.params.arguments.items():
                    span.set_attribute(
                        f"{MCPSpanAttributes.MCP_REQUEST_ARGUMENT}.{arg_name}",
                        McpInstrumentor.serialize(arg_val),
                    )

        elif isinstance(message, types.GetPromptRequest):
            prompt_name = message.params.name
            span.update_name(f"{MCPMethodValue.PROMPTS_GET} {prompt_name}")
            span.set_attribute(MCPSpanAttributes.MCP_PROMPT_NAME, prompt_name)

        elif isinstance(
            message,
            (
                types.ReadResourceRequest,
                types.SubscribeRequest,
                types.UnsubscribeRequest,
                types.ResourceUpdatedNotification,
            ),
        ):
            resource_uri = str(message.params.uri)
            span.update_name(f"{message.method} {resource_uri}")
            span.set_attribute(
                MCPSpanAttributes.MCP_RESOURCE_URI, resource_uri
            )

        else:
            # Generic message - use method name as span name
            span.update_name(message.method)

    @staticmethod
    def serialize(value: Any) -> str:
        """
        Serialize a value to JSON string for span attributes.

        Args:
            value: Value to serialize

        Returns:
            JSON string or empty string if serialization fails
        """
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return ""
