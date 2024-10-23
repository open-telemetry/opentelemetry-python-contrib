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
from collections import namedtuple

import pytest


from unittest.mock import MagicMock, patch
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)


from opentelemetry.semconv.trace import SpanAttributes

from opentelemetry.instrumentation.logging import (  # pylint: disable=no-name-in-module
    DEFAULT_LOGGING_FORMAT,
    LoggingInstrumentor,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import (
    NoOpTracerProvider,
    ProxyTracer,
    get_tracer,
    get_current_span,
)

from handlers.opentelemetry_loguru.src.exporter import LoguruHandler, _STD_TO_OTEL

from opentelemetry._logs import get_logger_provider


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
            self.assert_trace_context_injected(span_id, trace_id, trace_sampled)

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
    def test_custom_format_and_level_api(self, basic_config_mock):  # pylint: disable=no-self-use
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
            self.assert_trace_context_injected(span_id, trace_id, trace_sampled)

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


class TimestampRecord:
    def __init__(self, data):
        self.timestam = data

    def timestamp(self):
        return self.timestam


class TestLoguruHandler(TestBase):
    def setUp(self):
        self.default_provider = get_logger_provider()
        self.custom_provider = MagicMock()

        RecordFile = namedtuple("RecordFile", ["path", "name"])
        file_record = RecordFile(path="test_file.py", name="test_file.py")

        RecordProcess = namedtuple("RecordProcess", ["name", "id"])
        process_record = RecordProcess(name="MainProcess", id=1)

        RecordThread = namedtuple("RecordThread", ["name", "id"])
        thread_record = RecordThread(name="MainThread", id=1)

        timeRec = TimestampRecord(data=2.38763786)

        self.record = {
            "time": timeRec,
            "level": MagicMock(name="ERROR", no=40),
            "message": "Test message",
            "file": file_record,
            "process": process_record,
            "thread": thread_record,
            "function": "test_function",
            "line": 123,
            "exception": None,
        }

        self.span_context = get_current_span().get_span_context()
        self.current_span = MagicMock()
        self.current_span.get_span_context.return_value = self.span_context

    def test_attributes_extraction_without_exception(self):
        handler = LoguruHandler(
            service_name="flask-loguru-demo",
            server_hostname="instance-1",
            exporter=OTLPLogExporter(insecure=True),
        )

        attrs = handler._get_attributes(self.record)

        expected_attrs = {
            SpanAttributes.CODE_FILEPATH: "test_file.py",
            SpanAttributes.CODE_FUNCTION: "test_function",
            SpanAttributes.CODE_LINENO: 123,
        }

        self.assertEqual(
            attrs[SpanAttributes.CODE_FILEPATH],
            expected_attrs[SpanAttributes.CODE_FILEPATH],
        )
        self.assertEqual(
            attrs[SpanAttributes.CODE_FUNCTION],
            expected_attrs[SpanAttributes.CODE_FUNCTION],
        )
        self.assertEqual(
            attrs[SpanAttributes.CODE_LINENO],
            expected_attrs[SpanAttributes.CODE_LINENO],
        )

    @patch("traceback.format_exception")
    def test_attributes_extraction_with_exception(self, mock_format_exception):
        mock_format_exception.return_value = "Exception traceback"
        exception = Exception("Test exception")

        ExceptionRecord = namedtuple("ExceptionRecord", ["type", "value", "traceback"])

        # Example usage:
        exception_record = ExceptionRecord(
            type=type(exception).__name__,
            value=str(exception),
            traceback=mock_format_exception(exception),
        )
        self.record["exception"] = exception_record

        handler = LoguruHandler(
            service_name="flask-loguru-demo",
            server_hostname="instance-1",
            exporter=OTLPLogExporter(insecure=True),
        )

        attrs = handler._get_attributes(self.record)

        expected_attrs = {
            SpanAttributes.CODE_FILEPATH: "test_file.py",
            SpanAttributes.CODE_FUNCTION: "test_function",
            SpanAttributes.CODE_LINENO: 123,
            SpanAttributes.EXCEPTION_TYPE: "Exception",
            SpanAttributes.EXCEPTION_MESSAGE: "Test exception",
            SpanAttributes.EXCEPTION_STACKTRACE: "Exception traceback",
        }

        self.assertEqual(
            attrs[SpanAttributes.EXCEPTION_TYPE],
            expected_attrs[SpanAttributes.EXCEPTION_TYPE],
        )
        self.assertEqual(
            attrs[SpanAttributes.EXCEPTION_MESSAGE],
            expected_attrs[SpanAttributes.EXCEPTION_MESSAGE],
        )
        self.assertEqual(
            attrs[SpanAttributes.EXCEPTION_STACKTRACE],
            expected_attrs[SpanAttributes.EXCEPTION_STACKTRACE],
        )

    @patch("opentelemetry.trace.get_current_span")
    def test_translation(self, mock_get_current_span):
        mock_get_current_span.return_value = self.current_span

        handler = LoguruHandler(
            service_name="flask-loguru-demo",
            server_hostname="instance-1",
            exporter=OTLPLogExporter(insecure=True),
        )

        log_record = handler._translate(self.record)
        self.assertEqual(log_record.trace_id, self.span_context.trace_id)
        self.assertEqual(log_record.span_id, self.span_context.span_id)
        self.assertEqual(log_record.trace_flags, self.span_context.trace_flags)
        self.assertEqual(
            log_record.severity_number, _STD_TO_OTEL[self.record["level"].no]
        )
        self.assertEqual(log_record.body, self.record["message"])

    @patch("opentelemetry._logs.Logger.emit")
    @patch("opentelemetry.trace.get_current_span")
    def test_sink(self, mock_get_current_span, mock_emit):
        mock_get_current_span.return_value = self.current_span

        handler = LoguruHandler(
            service_name="flask-loguru-demo",
            server_hostname="instance-1",
            exporter=OTLPLogExporter(insecure=True),
        )

        MessageRecord = namedtuple("MessageRecord", ["record"])
        message = MessageRecord(record=self.record)

        handler.sink(message)

    def test_no_op_tracer_provider(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(tracer_provider=NoOpTracerProvider())

        with self.caplog.at_level(level=logging.INFO):
            logger = logging.getLogger("test logger")
            logger.info("hello")

            self.assertEqual(len(self.caplog.records), 1)
            record = self.caplog.records[0]
            self.assertEqual(record.otelSpanID, "0")
            self.assertEqual(record.otelTraceID, "0")
            self.assertEqual(record.otelServiceName, "")
            self.assertEqual(record.otelTraceSampled, False)
