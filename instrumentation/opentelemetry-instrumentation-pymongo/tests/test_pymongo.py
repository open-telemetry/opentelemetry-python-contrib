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

from unittest import mock

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.pymongo import (
    CommandTracer,
    PymongoInstrumentor,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase


class TestPymongo(TestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.start_callback = mock.MagicMock()
        self.success_callback = mock.MagicMock()
        self.failed_callback = mock.MagicMock()

    def test_pymongo_instrumentor(self):
        mock_register = mock.Mock()
        patch = mock.patch(
            "pymongo.monitoring.register", side_effect=mock_register
        )
        with patch:
            PymongoInstrumentor().instrument()
        self.assertTrue(mock_register.called)

    def test_started(self):
        command_attrs = {
            "command_name": "find",
        }
        command_tracer = CommandTracer(
            self.tracer, request_hook=self.start_callback
        )
        mock_event = MockEvent(
            command_attrs, ("test.com", "1234"), "test_request_id"
        )
        command_tracer.started(event=mock_event)
        # the memory exporter can't be used here because the span isn't ended
        # yet
        # pylint: disable=protected-access
        span = command_tracer._pop_span(mock_event)
        self.assertIs(span.kind, trace_api.SpanKind.CLIENT)
        self.assertEqual(span.name, "database_name.find")
        self.assertEqual(span.attributes[SpanAttributes.DB_SYSTEM], "mongodb")
        self.assertEqual(
            span.attributes[SpanAttributes.DB_NAME], "database_name"
        )
        self.assertEqual(span.attributes[SpanAttributes.DB_STATEMENT], "find")
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME], "test.com"
        )
        self.assertEqual(span.attributes[SpanAttributes.NET_PEER_PORT], "1234")
        self.start_callback.assert_called_once_with(span, mock_event)

    def test_succeeded(self):
        mock_event = MockEvent({})
        command_tracer = CommandTracer(
            self.tracer,
            request_hook=self.start_callback,
            response_hook=self.success_callback,
        )
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertIs(span.status.status_code, trace_api.StatusCode.UNSET)
        self.assertIsNotNone(span.end_time)
        self.start_callback.assert_called_once()
        self.success_callback.assert_called_once()

    def test_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        mock_event = MockEvent({})
        command_tracer = CommandTracer(mock_tracer)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)
        self.assertFalse(mock_span.is_recording())
        self.assertTrue(mock_span.is_recording.called)
        self.assertFalse(mock_span.set_attribute.called)
        self.assertFalse(mock_span.set_status.called)

    def test_suppression_key(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = True
        mock_tracer.start_span.return_value = mock_span
        mock_event = MockEvent({})
        mock_event.command.get = mock.Mock()
        mock_event.command.get.return_value = "dummy"

        with suppress_instrumentation():
            command_tracer = CommandTracer(mock_tracer)
            command_tracer.started(event=mock_event)
            command_tracer.succeeded(event=mock_event)

        # if suppression key is set, CommandTracer methods return immediately, so command.get is not invoked.
        self.assertFalse(
            mock_event.command.get.called  # pylint: disable=no-member
        )

    def test_failed(self):
        mock_event = MockEvent({})
        command_tracer = CommandTracer(
            self.tracer,
            request_hook=self.start_callback,
            failed_hook=self.failed_callback,
        )
        command_tracer.started(event=mock_event)
        command_tracer.failed(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(
            span.status.status_code,
            trace_api.StatusCode.ERROR,
        )
        self.assertEqual(span.status.description, "failure")
        self.assertIsNotNone(span.end_time)
        self.start_callback.assert_called_once()
        self.failed_callback.assert_called_once()

    def test_multiple_commands(self):
        first_mock_event = MockEvent({}, ("firstUrl", "123"), "first")
        second_mock_event = MockEvent({}, ("secondUrl", "456"), "second")
        command_tracer = CommandTracer(self.tracer)
        command_tracer.started(event=first_mock_event)
        command_tracer.started(event=second_mock_event)
        command_tracer.succeeded(event=first_mock_event)
        command_tracer.failed(event=second_mock_event)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 2)
        first_span = spans_list[0]
        second_span = spans_list[1]

        self.assertIs(
            first_span.status.status_code,
            trace_api.StatusCode.UNSET,
        )
        self.assertIs(
            second_span.status.status_code,
            trace_api.StatusCode.ERROR,
        )

    def test_int_command(self):
        command_attrs = {
            "command_name": 123,
        }
        mock_event = MockEvent(command_attrs)

        command_tracer = CommandTracer(self.tracer)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "database_name.123")

    def test_no_op_tracer(self):
        mock_event = MockEvent({})

        tracer = trace_api.NoOpTracer()
        command_tracer = CommandTracer(tracer)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_capture_statement_getmore(self):
        command_attrs = {
            "command_name": "getMore",
            "collection": "test_collection",
        }
        mock_event = MockEvent(command_attrs)

        command_tracer = CommandTracer(self.tracer, capture_statement=True)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(
            span.attributes[SpanAttributes.DB_STATEMENT],
            "getMore test_collection",
        )

    def test_capture_statement_aggregate(self):
        pipeline = [
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        ]
        command_attrs = {
            "command_name": "aggregate",
            "pipeline": pipeline,
        }
        command_tracer = CommandTracer(self.tracer, capture_statement=True)
        mock_event = MockEvent(command_attrs)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        expected_statement = f"aggregate {pipeline}"
        self.assertEqual(
            span.attributes[SpanAttributes.DB_STATEMENT], expected_statement
        )

    def test_capture_statement_disabled_getmore(self):
        command_attrs = {
            "command_name": "getMore",
            "collection": "test_collection",
        }
        command_tracer = CommandTracer(self.tracer, capture_statement=False)
        mock_event = MockEvent(command_attrs)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(
            span.attributes[SpanAttributes.DB_STATEMENT], "getMore"
        )

    def test_capture_statement_disabled_aggregate(self):
        pipeline = [{"$match": {"status": "active"}}]
        command_attrs = {
            "command_name": "aggregate",
            "pipeline": pipeline,
        }
        command_tracer = CommandTracer(self.tracer, capture_statement=False)
        mock_event = MockEvent(command_attrs)
        command_tracer.started(event=mock_event)
        command_tracer.succeeded(event=mock_event)

        spans_list = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(
            span.attributes[SpanAttributes.DB_STATEMENT], "aggregate"
        )


class MockCommand:
    def __init__(self, command_attrs):
        self.command_attrs = command_attrs

    def get(self, key, default=""):
        return self.command_attrs.get(key, default)


class MockEvent:
    def __init__(self, command_attrs, connection_id=None, request_id=""):
        self.command = MockCommand(command_attrs)
        self.command_name = self.command.get("command_name")
        self.connection_id = connection_id
        self.request_id = request_id

    def __getattr__(self, item):
        return item
