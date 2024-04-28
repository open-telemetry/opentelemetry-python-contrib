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

import logging
from typing import Optional
from unittest import mock
import unittest
from collections import namedtuple

import pytest

# Imports for StructlogHandler tests
from unittest.mock import Mock
from handlers.opentelemetry_structlog.src.exporter import LogExporter

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch



from opentelemetry.semconv.trace import SpanAttributes

from opentelemetry.instrumentation.logging import (  # pylint: disable=no-name-in-module
    DEFAULT_LOGGING_FORMAT,
    LoggingInstrumentor,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import ProxyTracer, get_tracer, get_current_span, SpanContext, TraceFlags

from handlers.opentelemetry_structlog.src.exporter import StructlogHandler
from handlers.opentelemetry_loguru.src.exporter import LoguruHandler, _STD_TO_OTEL

from opentelemetry._logs import get_logger_provider, get_logger
import time

class FakeTracerProvider:
    def get_tracer(  # pylint: disable=no-self-use
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: Optional[str] = None,
        schema_url: Optional[str] = None,
    ) -> ProxyTracer:
        return ProxyTracer(
            instrumenting_module_name,
            instrumenting_library_version,
            schema_url,
        )


class TestLoggingInstrumentorProxyTracerProvider(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog  # pylint: disable=attribute-defined-outside-init

    def setUp(self):
        super().setUp()
        LoggingInstrumentor().instrument(tracer_provider=FakeTracerProvider())

    def tearDown(self):
        super().tearDown()
        LoggingInstrumentor().uninstrument()

    def test_trace_context_injection(self):
        with self.caplog.at_level(level=logging.INFO):
            logger = logging.getLogger("test logger")
            logger.info("hello")
            self.assertEqual(len(self.caplog.records), 1)
            record = self.caplog.records[0]
            self.assertEqual(record.otelSpanID, "0")
            self.assertEqual(record.otelTraceID, "0")
            self.assertEqual(record.otelServiceName, "")
            self.assertEqual(record.otelTraceSampled, False)


def log_hook(span, record):
    record.custom_user_attribute_from_log_hook = "some-value"


class TestLoggingInstrumentor(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog  # pylint: disable=attribute-defined-outside-init

    def setUp(self):
        super().setUp()
        LoggingInstrumentor().instrument()
        self.tracer = get_tracer(__name__)

    def tearDown(self):
        super().tearDown()
        LoggingInstrumentor().uninstrument()

    def assert_trace_context_injected(self, span_id, trace_id, trace_sampled):
        with self.caplog.at_level(level=logging.INFO):
            logger = logging.getLogger("test logger")
            logger.info("hello")
            self.assertEqual(len(self.caplog.records), 1)
            record = self.caplog.records[0]
            self.assertEqual(record.otelSpanID, span_id)
            self.assertEqual(record.otelTraceID, trace_id)
            self.assertEqual(record.otelTraceSampled, trace_sampled)
            self.assertEqual(record.otelServiceName, "unknown_service")

    def test_trace_context_injection(self):
        with self.tracer.start_as_current_span("s1") as span:
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_sampled = span.get_span_context().trace_flags.sampled
            self.assert_trace_context_injected(
                span_id, trace_id, trace_sampled
            )

    def test_trace_context_injection_without_span(self):
        self.assert_trace_context_injected("0", "0", False)

    @mock.patch("logging.basicConfig")
    def test_basic_config_called(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        self.assertFalse(basic_config_mock.called)
        LoggingInstrumentor().uninstrument()

        env_patch = mock.patch.dict(
            "os.environ", {"OTEL_PYTHON_LOG_CORRELATION": "true"}
        )
        env_patch.start()
        LoggingInstrumentor().instrument()
        basic_config_mock.assert_called_with(
            format=DEFAULT_LOGGING_FORMAT, level=logging.INFO
        )
        env_patch.stop()

    @mock.patch("logging.basicConfig")
    def test_custom_format_and_level_env(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        self.assertFalse(basic_config_mock.called)
        LoggingInstrumentor().uninstrument()

        env_patch = mock.patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_LOG_CORRELATION": "true",
                "OTEL_PYTHON_LOG_FORMAT": "%(message)s %(otelSpanID)s",
                "OTEL_PYTHON_LOG_LEVEL": "error",
            },
        )
        env_patch.start()
        LoggingInstrumentor().instrument()
        basic_config_mock.assert_called_with(
            format="%(message)s %(otelSpanID)s", level=logging.ERROR
        )
        env_patch.stop()

    @mock.patch("logging.basicConfig")
    def test_custom_format_and_level_api(
        self, basic_config_mock
    ):  # pylint: disable=no-self-use
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(
            set_logging_format=True,
            logging_format="%(message)s span_id=%(otelSpanID)s",
            log_level=logging.WARNING,
        )
        basic_config_mock.assert_called_with(
            format="%(message)s span_id=%(otelSpanID)s", level=logging.WARNING
        )

    def test_log_hook(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(
            set_logging_format=True,
            log_hook=log_hook,
        )
        with self.tracer.start_as_current_span("s1") as span:
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_sampled = span.get_span_context().trace_flags.sampled
            with self.caplog.at_level(level=logging.INFO):
                logger = logging.getLogger("test logger")
                logger.info("hello")
                self.assertEqual(len(self.caplog.records), 1)
                record = self.caplog.records[0]
                self.assertEqual(record.otelSpanID, span_id)
                self.assertEqual(record.otelTraceID, trace_id)
                self.assertEqual(record.otelServiceName, "unknown_service")
                self.assertEqual(record.otelTraceSampled, trace_sampled)
                self.assertEqual(
                    record.custom_user_attribute_from_log_hook, "some-value"
                )

    def test_uninstrumented(self):
        with self.tracer.start_as_current_span("s1") as span:
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_sampled = span.get_span_context().trace_flags.sampled
            self.assert_trace_context_injected(
                span_id, trace_id, trace_sampled
            )

        LoggingInstrumentor().uninstrument()

        self.caplog.clear()
        with self.tracer.start_as_current_span("s1") as span:
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_sampled = span.get_span_context().trace_flags.sampled
            with self.caplog.at_level(level=logging.INFO):
                logger = logging.getLogger("test logger")
                logger.info("hello")
                self.assertEqual(len(self.caplog.records), 1)
                record = self.caplog.records[0]
                self.assertFalse(hasattr(record, "otelSpanID"))
                self.assertFalse(hasattr(record, "otelTraceID"))
                self.assertFalse(hasattr(record, "otelServiceName"))
                self.assertFalse(hasattr(record, "otelTraceSampled"))

# StructlogHandler Tests
# Test Initialization
class TestStructlogHandler(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog  # pylint: disable=attribute-defined-outside-init
    
    def mocker(self):
        return MagicMock()

    def setUp(self):
        super().setUp()
        LoggingInstrumentor().instrument()
        self.tracer = get_tracer(__name__)

    def tearDown(self):
        super().tearDown()
        LoggingInstrumentor().uninstrument()

    def structlog_exporter(self):
        with self.caplog.at_level(level=logging.INFO):
            # Mock the LogExporter dependency
            mock_exporter = Mock(spec=LogExporter)
            # Instantiate the StructlogHandler with mock dependencies
            exporter = StructlogHandler("test_service", "test_host", mock_exporter)
            return exporter


    def test_initialization(self):
        exporter = self.structlog_exporter()
        assert exporter._logger_provider is not None, "LoggerProvider should be initialized"
        assert exporter._logger is not None, "Logger should be initialized"

    def test_pre_process_adds_timestamp(self):
        event_dict = {"event": "test_event"}
        processed_event = self.structlog_exporter()._pre_process(event_dict)
        assert "timestamp" in processed_event, "Timestamp should be added in pre-processing"

    def test_post_process_formats_timestamp(self):
        # Assuming the pre_process method has added a datetime object
        event_dict = {"timestamp": datetime.now(timezone.utc)}
        processed_event = self.structlog_exporter()._post_process(event_dict)
        assert isinstance(processed_event["timestamp"], str), "Timestamp should be formatted to string in ISO format"

    def test_parse_exception(self):
        # Mocking an exception event
        exception = (ValueError, ValueError("mock error"), None)
        event_dict = {"exception": exception}
        parsed_exception = self.structlog_exporter()._parse_exception(event_dict)
        assert parsed_exception["exception.type"] == "ValueError", "Exception type should be parsed"
        assert parsed_exception["exception.message"] == "mock error", "Exception message should be parsed"
        # Further assertions can be added for stack trace

    def test_parse_timestamp(self):
        # Assuming a specific datetime for consistency
        fixed_datetime = datetime(2020, 1, 1, tzinfo=timezone.utc)
        event_dict = {"timestamp": fixed_datetime}
        timestamp = self.structlog_exporter()._parse_timestamp(event_dict)
        expected_timestamp = 1577836800000000000  # Expected nanoseconds since epoch
        assert timestamp == expected_timestamp, "Timestamp should be correctly parsed to nanoseconds"

    def test_call_method_processes_log_correctly(self):
        # Mock the logger and exporter
        exporter = MagicMock()
        logger = MagicMock()
        exporter_instance = StructlogHandler("test_service", "test_host", exporter)
        exporter_instance._logger = logger

        # Define an event dictionary
        event_dict = {"level": "info", "event": "test event", "timestamp": datetime.now(timezone.utc)}

        # Call the __call__ method of StructlogHandler
        processed_event = exporter_instance(logger=None, name=None, event_dict=event_dict)

        # Assert that the logger's emit method was called with the processed event
        logger.emit.assert_called_once()





class TestLoguruHandler(TestBase):
    def setUp(self):
        self.default_provider = get_logger_provider()
        self.custom_provider = MagicMock()
        self.record = {
            "time": 1581000000.000123,
            "level": MagicMock(name="ERROR", no=40),
            "message": "Test message",
            "file": "test_file.py",
            "function": "test_function",
            "line": 123,
            "exception": None
        }
        # self.span_context = SpanContext(
        #     trace_id=1234,
        #     span_id=5678,
        #     trace_flags=TraceFlags(1),
        #     is_remote=False
        # )
        self.span_context = get_current_span().get_span_context()
        self.current_span = MagicMock()
        self.current_span.get_span_context.return_value = self.span_context

    def test_initialization_with_default_provider(self):
        handler = LoguruHandler()
        self.assertEqual(handler._logger_provider, self.default_provider)

    def test_initialization_with_custom_provider(self):
        handler = LoguruHandler(logger_provider=self.custom_provider)
        self.assertEqual(handler._logger_provider, self.custom_provider)

    def test_attributes_extraction_without_exception(self):
        attrs = LoguruHandler()._get_attributes(self.record)
        expected_attrs = {
            SpanAttributes.CODE_FILEPATH: 'test_file.py',
            SpanAttributes.CODE_FUNCTION: 'test_function',
            SpanAttributes.CODE_LINENO: 123
        }
        
        self.assertEqual(attrs[SpanAttributes.CODE_FILEPATH], expected_attrs[SpanAttributes.CODE_FILEPATH])
        self.assertEqual(attrs[SpanAttributes.CODE_FUNCTION], expected_attrs[SpanAttributes.CODE_FUNCTION])
        self.assertEqual(attrs[SpanAttributes.CODE_LINENO], expected_attrs[SpanAttributes.CODE_LINENO])

    @patch('traceback.format_exception')
    def test_attributes_extraction_with_exception(self, mock_format_exception):
        mock_format_exception.return_value = 'Exception traceback'
        exception = Exception("Test exception")
        
        ExceptionRecord = namedtuple('ExceptionRecord', ['type', 'value', 'traceback'])

# Example usage:
        exception_record = ExceptionRecord(
            type=type(exception).__name__,
            value=str(exception),
            traceback=mock_format_exception(exception)
        )
        self.record['exception'] = exception_record
        # self.record['exception'].type = type(exception).__name__
        # self.record['exception'].value = str(exception)
        # self.record['exception'].traceback = mock_format_exception(exception)
        
        attrs = LoguruHandler()._get_attributes(self.record)
        
        expected_attrs = {
            SpanAttributes.CODE_FILEPATH: 'test_file.py',
            SpanAttributes.CODE_FUNCTION: 'test_function',
            SpanAttributes.CODE_LINENO: 123,
            SpanAttributes.EXCEPTION_TYPE: 'Exception',
            SpanAttributes.EXCEPTION_MESSAGE: 'Test exception',
            SpanAttributes.EXCEPTION_STACKTRACE: 'Exception traceback'
        }
        
        self.assertEqual(attrs[SpanAttributes.EXCEPTION_TYPE], expected_attrs[SpanAttributes.EXCEPTION_TYPE])
        self.assertEqual(attrs[SpanAttributes.EXCEPTION_MESSAGE], expected_attrs[SpanAttributes.EXCEPTION_MESSAGE])
        self.assertEqual(attrs[SpanAttributes.EXCEPTION_STACKTRACE], expected_attrs[SpanAttributes.EXCEPTION_STACKTRACE])

    @patch('opentelemetry.trace.get_current_span')
    def test_translation(self, mock_get_current_span):
        mock_get_current_span.return_value = self.current_span
        handler = LoguruHandler(logger_provider=self.custom_provider)
        log_record = handler._translate(self.record)
        self.assertEqual(log_record.trace_id, self.span_context.trace_id)
        self.assertEqual(log_record.span_id, self.span_context.span_id)
        self.assertEqual(log_record.trace_flags, self.span_context.trace_flags)
        self.assertEqual(log_record.severity_number, _STD_TO_OTEL[self.record["level"].no])
        self.assertEqual(log_record.body, self.record["message"])

    @patch('opentelemetry._logs.Logger.emit')
    @patch('opentelemetry.trace.get_current_span')
    def test_sink(self, mock_get_current_span, mock_emit):
        mock_get_current_span.return_value = self.current_span
        handler = LoguruHandler(logger_provider=self.custom_provider)
        handler.sink(self.record)
        #mock_emit.assert_called_once()
        handler._logger.emit.assert_called_once()

# # Running the tests
# if __name__ == '__main__':
#     unittest.main()


