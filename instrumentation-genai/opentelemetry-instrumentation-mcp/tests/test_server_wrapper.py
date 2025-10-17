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

"""Tests for server-side wrapper methods."""

import asyncio
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.mcp import McpInstrumentor
from opentelemetry.trace import SpanKind


class MockIncomingRequest:
    """Mock incoming request from client."""

    def __init__(
        self,
        method: str = "tools/call",
        has_id: bool = True,
        has_meta: bool = False,
    ) -> None:
        self.method = method
        self.id = 123 if has_id else None
        self.params = MagicMock()
        if has_meta:
            self.params.meta = MagicMock()
            self.params.meta.model_dump.return_value = {
                "traceparent": "00-trace-span-01"
            }
        else:
            self.params.meta = None


class MockIncomingNotification:
    """Mock incoming notification from client."""

    def __init__(
        self, method: str = "notifications/initialized", has_meta: bool = False
    ) -> None:
        self.method = method
        self.params = MagicMock()
        if has_meta:
            self.params.meta = MagicMock()
            self.params.meta.model_dump.return_value = {
                "traceparent": "00-trace-span-01"
            }
        else:
            self.params.meta = None


class TestWrapServerHandleRequest(unittest.TestCase):
    """Test _wrap_server_handle_request method."""

    def setUp(self):
        self.instrumentor = McpInstrumentor()

    def test_wrap_server_handle_request_no_request(self) -> None:
        """Test wrapper with no request in args."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        result = asyncio.run(
            self.instrumentor._wrap_server_handle_request(
                mock_wrapped, mock_instance, ("session",), {}
            )
        )
        self.assertEqual(result, {"result": "success"})

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_handle_request_with_request(
        self, mock_generate_attrs: MagicMock
    ):
        """Test wrapper with valid request."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        incoming_req = MockIncomingRequest()

        result = asyncio.run(
            self.instrumentor._wrap_server_handle_request(
                mock_wrapped, mock_instance, ("session", incoming_req), {}
            )
        )

        # Verify the method completes and returns result
        self.assertEqual(result, {"result": "success"})


class TestWrapServerHandleNotification(unittest.TestCase):
    """Test _wrap_server_handle_notification method."""

    def setUp(self):
        self.instrumentor = McpInstrumentor()

    def test_wrap_server_handle_notification_no_notification(self) -> None:
        """Test wrapper with no notification in args."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        result = asyncio.run(
            self.instrumentor._wrap_server_handle_notification(
                mock_wrapped, mock_instance, (), {}
            )
        )
        self.assertEqual(result, {"result": "success"})

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_handle_notification_with_notification(
        self, mock_generate_attrs: MagicMock
    ):
        """Test wrapper with valid notification."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        incoming_notif = MockIncomingNotification()

        result = asyncio.run(
            self.instrumentor._wrap_server_handle_notification(
                mock_wrapped, mock_instance, (incoming_notif,), {}
            )
        )

        # Verify the method completes and returns result
        self.assertEqual(result, {"result": "success"})


class TestWrapServerMessageHandler(unittest.TestCase):
    """Test _wrap_server_message_handler method."""

    def setUp(self):
        self.instrumentor = McpInstrumentor()

    def test_wrap_server_message_handler_no_message(self) -> None:
        """Test handler with no incoming message."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        result = asyncio.run(
            self.instrumentor._wrap_server_message_handler(
                mock_wrapped, mock_instance, (), {}, incoming_msg=None
            )
        )
        self.assertEqual(result, {"result": "success"})

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_message_handler_with_request_id(
        self, mock_generate_attrs: MagicMock
    ):
        """Test handler extracts request ID from request."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        incoming_msg = MockIncomingRequest(has_id=True)

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_server_message_handler(
                    mock_wrapped,
                    mock_instance,
                    (),
                    {},
                    incoming_msg=incoming_msg,
                )
            )

            # Verify span was created with SERVER kind
            call_kwargs = mock_span_ctx.call_args[1]
            self.assertEqual(call_kwargs["kind"], SpanKind.SERVER)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_message_handler_without_request_id(
        self, mock_generate_attrs: MagicMock
    ):
        """Test handler works without request ID (notification)."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        incoming_msg = MockIncomingNotification()

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_server_message_handler(
                    mock_wrapped,
                    mock_instance,
                    (),
                    {},
                    incoming_msg=incoming_msg,
                )
            )

            mock_span_ctx.assert_called_once()

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_message_handler_extracts_trace_context(
        self, mock_generate_attrs: MagicMock
    ):
        """Test handler extracts trace context from message meta."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        incoming_msg = MockIncomingRequest(has_meta=True)

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            with patch.object(
                self.instrumentor.propagators, "extract"
            ) as mock_extract:
                mock_extract.return_value = MagicMock()

                asyncio.run(
                    self.instrumentor._wrap_server_message_handler(
                        mock_wrapped,
                        mock_instance,
                        (),
                        {},
                        incoming_msg=incoming_msg,
                    )
                )

                # Verify extract was called with carrier
                mock_extract.assert_called_once()
                call_kwargs = mock_extract.call_args[1]
                self.assertIn("carrier", call_kwargs)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_message_handler_success_status(
        self, mock_generate_attrs: MagicMock
    ):
        """Test handler sets OK status on success."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        incoming_msg = MockIncomingRequest()

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            result = asyncio.run(
                self.instrumentor._wrap_server_message_handler(
                    mock_wrapped,
                    mock_instance,
                    (),
                    {},
                    incoming_msg=incoming_msg,
                )
            )

            self.assertEqual(result, {"result": "success"})
            mock_span.set_status.assert_called_once()

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_server_message_handler_error_status(
        self, mock_generate_attrs: MagicMock
    ):
        """Test handler sets ERROR status and records exception."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Test error")

        mock_instance = MagicMock()
        incoming_msg = MockIncomingRequest()

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            with self.assertRaises(RuntimeError):
                asyncio.run(
                    self.instrumentor._wrap_server_message_handler(
                        mock_wrapped,
                        mock_instance,
                        (),
                        {},
                        incoming_msg=incoming_msg,
                    )
                )

            mock_span.set_status.assert_called_once()
            mock_span.record_exception.assert_called_once()


class TestExtractSessionId(unittest.TestCase):
    """Test _extract_session_id method."""

    def setUp(self):
        self.instrumentor = McpInstrumentor()

    def test_extract_session_id_no_args(self) -> None:
        """Test extraction with no args."""
        result = self.instrumentor._extract_session_id(())
        self.assertIsNone(result)

    def test_extract_session_id_not_request_responder(self) -> None:
        """Test extraction with non-RequestResponder object."""
        mock_obj = MagicMock()
        result = self.instrumentor._extract_session_id((mock_obj,))
        self.assertIsNone(result)

    def test_extract_session_id_exception(self) -> None:
        """Test extraction handles exceptions gracefully."""
        mock_obj = MagicMock()
        mock_obj.side_effect = Exception("Test error")
        result = self.instrumentor._extract_session_id((mock_obj,))
        self.assertIsNone(result)
