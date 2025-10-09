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

"""Tests for McpInstrumentor core functionality."""

import unittest
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.mcp import McpInstrumentor
from opentelemetry.trace import TracerProvider


class TestMcpInstrumentorInit(unittest.TestCase):
    """Test McpInstrumentor initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        instrumentor = McpInstrumentor()
        self.assertIsNotNone(instrumentor)
        self.assertIsNotNone(instrumentor.tracer)
        self.assertIsNotNone(instrumentor.propagators)

    def test_init_with_tracer_provider(self) -> None:
        """Test initialization with custom tracer provider."""
        mock_provider = MagicMock(spec=TracerProvider)
        mock_tracer = MagicMock()
        mock_provider.get_tracer.return_value = mock_tracer

        with patch("opentelemetry.trace.get_tracer") as mock_get_tracer:
            mock_get_tracer.return_value = mock_tracer
            instrumentor = McpInstrumentor(tracer_provider=mock_provider)
            self.assertIsNotNone(instrumentor.tracer)

    def test_init_with_propagators(self) -> None:
        """Test initialization with custom propagators."""
        mock_propagators = MagicMock()
        instrumentor = McpInstrumentor(propagators=mock_propagators)
        self.assertEqual(instrumentor.propagators, mock_propagators)


class TestMcpInstrumentorDependencies(unittest.TestCase):
    """Test instrumentation dependencies."""

    def test_instrumentation_dependencies(self) -> None:
        """Test that instrumentation_dependencies returns correct packages."""
        instrumentor = McpInstrumentor()
        deps = instrumentor.instrumentation_dependencies()
        self.assertIsNotNone(deps)
        self.assertEqual(len(deps), 1)
        self.assertIn("mcp >= 1.8.1", deps)


class TestMcpInstrumentorInstrument(unittest.TestCase):
    """Test _instrument method."""

    def setUp(self):
        self.instrumentor = McpInstrumentor()

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.register_post_import_hook"
    )
    def test_instrument_registers_hooks(self, mock_register: MagicMock):
        """Test that _instrument registers all required hooks."""
        self.instrumentor._instrument()
        self.assertEqual(mock_register.call_count, 4)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.register_post_import_hook"
    )
    def test_instrument_registers_session_hooks(
        self, mock_register: MagicMock
    ):
        """Test that _instrument registers session hooks."""
        self.instrumentor._instrument()
        # Verify mcp.shared.session is registered (appears twice for send_request and send_notification)
        calls = [
            call[0][1] if len(call[0]) > 1 else None
            for call in mock_register.call_args_list
        ]
        session_calls = [c for c in calls if c == "mcp.shared.session"]
        self.assertEqual(len(session_calls), 2)

    @patch(
        "opentelemetry.instrumentation.mcp.instrumentation.register_post_import_hook"
    )
    def test_instrument_registers_server_hooks(self, mock_register: MagicMock):
        """Test that _instrument registers server hooks."""
        self.instrumentor._instrument()
        # Verify mcp.server.lowlevel.server is registered (appears twice for _handle_request and _handle_notification)
        calls = [
            call[0][1] if len(call[0]) > 1 else None
            for call in mock_register.call_args_list
        ]
        server_calls = [c for c in calls if c == "mcp.server.lowlevel.server"]
        self.assertEqual(len(server_calls), 2)


class TestMcpInstrumentorUninstrument(unittest.TestCase):
    """Test _uninstrument method."""

    def setUp(self):
        self.instrumentor = McpInstrumentor()

    @patch("opentelemetry.instrumentation.mcp.instrumentation.unwrap")
    def test_uninstrument_unwraps_all(self, mock_unwrap: MagicMock):
        """Test that _uninstrument unwraps all hooks."""
        self.instrumentor._uninstrument()
        self.assertEqual(mock_unwrap.call_count, 4)

    @patch("opentelemetry.instrumentation.mcp.instrumentation.unwrap")
    def test_uninstrument_unwraps_send_request(self, mock_unwrap: MagicMock):
        """Test that _uninstrument unwraps send_request."""
        self.instrumentor._uninstrument()
        mock_unwrap.assert_any_call(
            "mcp.shared.session", "BaseSession.send_request"
        )

    @patch("opentelemetry.instrumentation.mcp.instrumentation.unwrap")
    def test_uninstrument_unwraps_send_notification(
        self, mock_unwrap: MagicMock
    ):
        """Test that _uninstrument unwraps send_notification."""
        self.instrumentor._uninstrument()
        mock_unwrap.assert_any_call(
            "mcp.shared.session", "BaseSession.send_notification"
        )

    @patch("opentelemetry.instrumentation.mcp.instrumentation.unwrap")
    def test_uninstrument_unwraps_handle_request(self, mock_unwrap: MagicMock):
        """Test that _uninstrument unwraps handle_request."""
        self.instrumentor._uninstrument()
        mock_unwrap.assert_any_call(
            "mcp.server.lowlevel.server", "Server._handle_request"
        )

    @patch("opentelemetry.instrumentation.mcp.instrumentation.unwrap")
    def test_uninstrument_unwraps_handle_notification(
        self, mock_unwrap: MagicMock
    ):
        """Test that _uninstrument unwraps handle_notification."""
        self.instrumentor._uninstrument()
        mock_unwrap.assert_any_call(
            "mcp.server.lowlevel.server", "Server._handle_notification"
        )


class TestMcpInstrumentorSerialize(unittest.TestCase):
    """Test serialize static method."""

    def test_serialize_simple_dict(self) -> None:
        """Test serializing a simple dictionary."""
        result = McpInstrumentor.serialize({"key": "value"})
        self.assertEqual(result, '{"key": "value"}')

    def test_serialize_nested_dict(self) -> None:
        """Test serializing a nested dictionary."""
        result = McpInstrumentor.serialize({"outer": {"inner": "value"}})
        self.assertEqual(result, '{"outer": {"inner": "value"}}')

    def test_serialize_with_numbers(self) -> None:
        """Test serializing dictionary with numbers."""
        result = McpInstrumentor.serialize({"int": 42, "float": 3.14})
        self.assertIn('"int": 42', result)
        self.assertIn('"float": 3.14', result)

    def test_serialize_with_list(self) -> None:
        """Test serializing dictionary with list."""
        result = McpInstrumentor.serialize({"list": [1, 2, 3]})
        self.assertEqual(result, '{"list": [1, 2, 3]}')

    def test_serialize_empty_dict(self) -> None:
        """Test serializing empty dictionary."""
        result = McpInstrumentor.serialize({})
        self.assertEqual(result, "{}")

    def test_serialize_non_serializable(self) -> None:
        """Test serializing non-serializable object returns empty string."""

        class NonSerializable:
            pass

        result = McpInstrumentor.serialize({"obj": NonSerializable()})
        self.assertEqual(result, "")

    def test_serialize_with_none(self) -> None:
        """Test serializing dictionary with None value."""
        result = McpInstrumentor.serialize({"key": None})
        self.assertEqual(result, '{"key": null}')

    def test_serialize_with_boolean(self) -> None:
        """Test serializing dictionary with boolean values."""
        result = McpInstrumentor.serialize({"true": True, "false": False})
        self.assertIn('"true": true', result)
        self.assertIn('"false": false', result)
