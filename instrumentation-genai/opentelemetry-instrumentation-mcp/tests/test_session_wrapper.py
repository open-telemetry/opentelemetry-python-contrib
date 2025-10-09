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

"""Tests for _wrap_session_send method."""

import asyncio
import sys
import unittest
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.mcp import McpInstrumentor
from opentelemetry.trace import SpanKind


# Mock MCP types
class MockClientRequest:
    def __init__(
        self,
        method: str = "test_method",
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.params = params or {}

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return {"method": self.method, "params": self.params}

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "MockClientRequest":
        return cls(data.get("method", "test_method"), data.get("params", {}))


class MockClientNotification:
    def __init__(
        self,
        method: str = "test_notification",
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.params = params or {}

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return {"method": self.method, "params": self.params}

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "MockClientNotification":
        return cls(data.get("method", "test_method"), data.get("params", {}))


class MockServerRequest:
    def __init__(
        self,
        method: str = "test_method",
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.params = params or {}

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return {"method": self.method, "params": self.params}

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "MockServerRequest":
        return cls(data.get("method", "test_method"), data.get("params", {}))


class MockServerNotification:
    def __init__(
        self,
        method: str = "test_notification",
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        self.method = method
        self.params = params or {}

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return {"method": self.method, "params": self.params}

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "MockServerNotification":
        return cls(data.get("method", "test_method"), data.get("params", {}))


class TestWrapSessionSend(unittest.TestCase):
    """Test _wrap_session_send method."""

    def setUp(self) -> None:
        self.instrumentor: McpInstrumentor = McpInstrumentor()

        # Mock mcp.types module
        self.mock_types = MagicMock()
        self.mock_types.ClientRequest = MockClientRequest
        self.mock_types.ClientNotification = MockClientNotification
        self.mock_types.ServerRequest = MockServerRequest
        self.mock_types.ServerNotification = MockServerNotification
        sys.modules["mcp.types"] = self.mock_types

    def tearDown(self):
        if "mcp.types" in sys.modules:
            del sys.modules["mcp.types"]

    def test_wrap_session_send_no_message(self) -> None:
        """Test wrapper with no message in args."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        result = asyncio.run(
            self.instrumentor._wrap_session_send(
                mock_wrapped, mock_instance, (), {}
            )
        )
        self.assertEqual(result, {"result": "success"})

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_client_request(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test wrapper with ClientRequest creates CLIENT span."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> dict[str, str]:
            return {"result": "success"}

        mock_instance = MagicMock()
        mock_instance._request_id = 123
        message = MockClientRequest("tools/call", {"name": "test_tool"})

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_session_send(
                    mock_wrapped, mock_instance, (message,), {}
                )
            )

            mock_span_ctx.assert_called_once()
            call_kwargs = mock_span_ctx.call_args[1]
            self.assertEqual(call_kwargs["kind"], SpanKind.CLIENT)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_client_notification(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test wrapper with ClientNotification creates CLIENT span."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        message = MockClientNotification("notifications/initialized")

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_session_send(
                    mock_wrapped, mock_instance, (message,), {}
                )
            )

            call_kwargs = mock_span_ctx.call_args[1]
            self.assertEqual(call_kwargs["kind"], SpanKind.CLIENT)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_server_request(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test wrapper with ServerRequest creates SERVER span."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        message = MockServerRequest("tools/list")

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_session_send(
                    mock_wrapped, mock_instance, (message,), {}
                )
            )

            call_kwargs = mock_span_ctx.call_args[1]
            self.assertEqual(call_kwargs["kind"], SpanKind.SERVER)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_injects_trace_context(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test that trace context is injected into message."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            # Verify trace context was injected
            message: Any = args[0]
            message_dict: dict[str, Any] = message.model_dump()
            self.assertIn("params", message_dict)
            self.assertIn("_meta", message_dict["params"])
            return {"result": "success"}

        mock_instance = MagicMock()
        message = MockClientRequest("tools/call")

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_session_send(
                    mock_wrapped, mock_instance, (message,), {}
                )
            )

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_success_status(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test that successful execution sets OK status."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            return {"result": "success"}

        mock_instance = MagicMock()
        message = MockClientRequest("tools/call")

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            result: Any = asyncio.run(
                self.instrumentor._wrap_session_send(
                    mock_wrapped, mock_instance, (message,), {}
                )
            )

            self.assertEqual(result, {"result": "success"})
            mock_span.set_status.assert_called_once()

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_error_status(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test that exception sets ERROR status and records exception."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            raise ValueError("Test error")

        mock_instance = MagicMock()
        message = MockClientRequest("tools/call")

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            with self.assertRaises(ValueError):
                asyncio.run(
                    self.instrumentor._wrap_session_send(
                        mock_wrapped, mock_instance, (message,), {}
                    )
                )

            mock_span.set_status.assert_called_once()
            mock_span.record_exception.assert_called_once()

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.McpInstrumentor._generate_mcp_message_attrs"
    )
    def test_wrap_session_send_preserves_existing_params(
        self, mock_generate_attrs: MagicMock
    ) -> None:
        """Test that existing params are preserved."""

        async def mock_wrapped(*args: Any, **kwargs: Any) -> Any:
            message: Any = args[0]
            message_dict: dict[str, Any] = message.model_dump()
            # Verify existing param is still there
            self.assertEqual(message_dict["params"]["name"], "test_tool")
            return {"result": "success"}

        mock_instance = MagicMock()
        message = MockClientRequest("tools/call", {"name": "test_tool"})

        with patch.object(
            self.instrumentor.tracer, "start_as_current_span"
        ) as mock_span_ctx:
            mock_span = MagicMock()
            mock_span.__enter__ = MagicMock(return_value=mock_span)
            mock_span.__exit__ = MagicMock(return_value=None)
            mock_span_ctx.return_value = mock_span

            asyncio.run(
                self.instrumentor._wrap_session_send(
                    mock_wrapped, mock_instance, (message,), {}
                )
            )
