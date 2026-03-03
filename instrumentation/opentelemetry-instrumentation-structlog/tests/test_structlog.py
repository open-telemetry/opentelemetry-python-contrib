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

import sys

import structlog

from opentelemetry._logs import SeverityNumber
from opentelemetry.instrumentation.structlog import (
    OpenTelemetryProcessor,
    StructlogInstrumentor,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.semconv._incubating.attributes import exception_attributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import TraceFlags


class TestOpenTelemetryProcessor(TestBase):
    """Tests for the OpenTelemetryProcessor class."""

    def setUp(self):
        super().setUp()
        # Set up in-memory log exporter
        self.exporter = InMemoryLogRecordExporter()
        self.logger_provider = LoggerProvider()
        self.logger_provider.add_log_record_processor(
            SimpleLogRecordProcessor(self.exporter)
        )

        # Configure structlog with OTel processor
        self.processor = OpenTelemetryProcessor(
            logger_provider=self.logger_provider
        )
        structlog.configure(
            processors=[
                self.processor,
                structlog.dev.ConsoleRenderer(),
            ]
        )
        self.logger = structlog.get_logger()

    def tearDown(self):
        super().tearDown()
        # Reset structlog configuration
        structlog.reset_defaults()
        self.exporter.clear()

    def test_basic_log_emission(self):
        """Test that basic logs are emitted correctly."""
        self.logger.info("test message", user="alice", count=42)

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.log_record.body, "test message")
        self.assertEqual(log.log_record.severity_text, "INFO")
        self.assertEqual(log.log_record.severity_number, SeverityNumber.INFO)
        self.assertIn("user", log.log_record.attributes)
        self.assertEqual(log.log_record.attributes["user"], "alice")
        self.assertIn("count", log.log_record.attributes)
        self.assertEqual(log.log_record.attributes["count"], 42)

    def test_debug_level(self):
        """Test debug level mapping."""
        self.logger.debug("debug message")

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.log_record.severity_text, "DEBUG")
        self.assertEqual(log.log_record.severity_number, SeverityNumber.DEBUG)

    def test_info_level(self):
        """Test info level mapping."""
        self.logger.info("info message")

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.log_record.severity_text, "INFO")
        self.assertEqual(log.log_record.severity_number, SeverityNumber.INFO)

    def test_warning_level(self):
        """Test warning level mapping and normalization to WARN."""
        self.logger.warning("warning message")

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        # Should be normalized to "WARN" per OTel spec
        self.assertEqual(log.log_record.severity_text, "WARN")
        self.assertEqual(log.log_record.severity_number, SeverityNumber.WARN)

    def test_error_level(self):
        """Test error level mapping."""
        self.logger.error("error message")

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.log_record.severity_text, "ERROR")
        self.assertEqual(log.log_record.severity_number, SeverityNumber.ERROR)

    def test_critical_level(self):
        """Test critical level mapping."""
        self.logger.critical("critical message")

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.log_record.severity_text, "CRITICAL")
        self.assertEqual(log.log_record.severity_number, SeverityNumber.FATAL)

    def test_exception_from_exc_info_tuple(self):
        """Test exception extraction from exc_info tuple."""
        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()
            self.logger.error("error occurred", exc_info=exc_info)

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        attrs = log.log_record.attributes

        self.assertIn(exception_attributes.EXCEPTION_TYPE, attrs)
        self.assertEqual(attrs[exception_attributes.EXCEPTION_TYPE], "ValueError")

        self.assertIn(exception_attributes.EXCEPTION_MESSAGE, attrs)
        self.assertEqual(attrs[exception_attributes.EXCEPTION_MESSAGE], "test error")

        self.assertIn(exception_attributes.EXCEPTION_STACKTRACE, attrs)
        stacktrace = attrs[exception_attributes.EXCEPTION_STACKTRACE]
        self.assertIn("ValueError", stacktrace)
        self.assertIn("test error", stacktrace)

    def test_exception_from_exc_info_true(self):
        """Test exception extraction when exc_info=True."""
        try:
            raise RuntimeError("runtime error")
        except RuntimeError:
            self.logger.error("error occurred", exc_info=True)

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        attrs = log.log_record.attributes

        self.assertIn(exception_attributes.EXCEPTION_TYPE, attrs)
        self.assertEqual(attrs[exception_attributes.EXCEPTION_TYPE], "RuntimeError")

        self.assertIn(exception_attributes.EXCEPTION_MESSAGE, attrs)
        self.assertEqual(attrs[exception_attributes.EXCEPTION_MESSAGE], "runtime error")

        self.assertIn(exception_attributes.EXCEPTION_STACKTRACE, attrs)

    def test_exception_from_string(self):
        """Test exception from pre-rendered string (e.g., from ExceptionRenderer)."""
        exception_string = "Traceback (most recent call last):\n  File test.py\nValueError: test"
        self.logger.error("error occurred", exception=exception_string)

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        attrs = log.log_record.attributes

        self.assertIn(exception_attributes.EXCEPTION_STACKTRACE, attrs)
        self.assertEqual(
            attrs[exception_attributes.EXCEPTION_STACKTRACE],
            exception_string
        )

    def test_trace_context_with_active_span(self):
        """Test that trace context is captured with an active span."""
        with self.tracer.start_as_current_span("test-span") as span:
            self.logger.info("message in span")

            logs = self.exporter.get_finished_logs()
            self.assertEqual(len(logs), 1)

            log = logs[0]
            # Context should be set
            self.assertIsNotNone(log.log_record.trace_id)
            self.assertIsNotNone(log.log_record.span_id)

            # Should match the current span
            span_context = span.get_span_context()
            self.assertEqual(log.log_record.trace_id, span_context.trace_id)
            self.assertEqual(log.log_record.span_id, span_context.span_id)
            self.assertEqual(
                log.log_record.trace_flags,
                TraceFlags(span_context.trace_flags)
            )

    def test_without_active_span(self):
        """Test that logging works without an active span."""
        self.logger.info("message without span")

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        # Should still have a log record, just no trace context
        self.assertEqual(log.log_record.body, "message without span")

    def test_reserved_keys_filtered(self):
        """Test that structlog reserved keys are filtered from attributes."""
        # These keys should be filtered out
        self.logger.info(
            "test",
            user="alice",
            _record="should be filtered",
            _logger="should be filtered",
            _name="should be filtered",
        )

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        attrs = log.log_record.attributes

        # User attribute should be present
        self.assertIn("user", attrs)
        self.assertEqual(attrs["user"], "alice")

        # Reserved keys should be filtered
        self.assertNotIn("_record", attrs)
        self.assertNotIn("_logger", attrs)
        self.assertNotIn("_name", attrs)
        self.assertNotIn("event", attrs)
        self.assertNotIn("level", attrs)
        self.assertNotIn("timestamp", attrs)

    def test_custom_attributes_pass_through(self):
        """Test that custom attributes are passed through correctly."""
        self.logger.info(
            "test",
            user_id=123,
            request_id="abc-def",
            ip_address="192.168.1.1",
            duration=1.5,
            success=True,
        )

        logs = self.exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)

        log = logs[0]
        attrs = log.log_record.attributes

        self.assertEqual(attrs["user_id"], 123)
        self.assertEqual(attrs["request_id"], "abc-def")
        self.assertEqual(attrs["ip_address"], "192.168.1.1")
        self.assertEqual(attrs["duration"], 1.5)
        self.assertEqual(attrs["success"], True)

    def test_flush(self):
        """Test that flush calls force_flush on the provider."""
        # Create a mock provider to verify flush is called
        from unittest.mock import Mock

        mock_provider = Mock()
        mock_provider.force_flush = Mock()
        processor = OpenTelemetryProcessor(logger_provider=mock_provider)

        processor.flush()

        # Give the thread a moment to execute
        import time
        time.sleep(0.1)

        # Verify force_flush was called
        mock_provider.force_flush.assert_called_once()


class TestStructlogInstrumentor(TestBase):
    """Tests for the StructlogInstrumentor class."""

    def setUp(self):
        super().setUp()
        # Store original structlog config
        self.original_config = structlog.get_config()
        # Set up in-memory log exporter
        self.exporter = InMemoryLogRecordExporter()
        self.logger_provider = LoggerProvider()
        self.logger_provider.add_log_record_processor(
            SimpleLogRecordProcessor(self.exporter)
        )

    def tearDown(self):
        super().tearDown()
        # Uninstrument if needed
        if StructlogInstrumentor()._is_instrumented_by_opentelemetry:
            StructlogInstrumentor().uninstrument()
        # Reset structlog
        structlog.reset_defaults()
        self.exporter.clear()

    def test_instrument_adds_processor(self):
        """Test that instrument() adds the OTel processor to the chain."""
        # Configure structlog with a simple processor chain
        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer(),
            ]
        )

        # Get initial processor count
        initial_processors = structlog.get_config()["processors"]
        initial_count = len(initial_processors)

        # Instrument
        StructlogInstrumentor().instrument(logger_provider=self.logger_provider)

        # Check that processor was added
        new_processors = structlog.get_config()["processors"]
        self.assertEqual(len(new_processors), initial_count + 1)

        # Check that an OpenTelemetryProcessor is in the chain
        has_otel_processor = any(
            isinstance(p, OpenTelemetryProcessor) for p in new_processors
        )
        self.assertTrue(has_otel_processor)

    def test_uninstrument_removes_processor(self):
        """Test that uninstrument() removes the OTel processor."""
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer(),
            ]
        )

        # Instrument
        StructlogInstrumentor().instrument(logger_provider=self.logger_provider)

        # Verify processor was added
        config_after_instrument = structlog.get_config()["processors"]
        has_otel = any(
            isinstance(p, OpenTelemetryProcessor) for p in config_after_instrument
        )
        self.assertTrue(has_otel)

        # Uninstrument
        StructlogInstrumentor().uninstrument()

        # Verify processor was removed
        config_after_uninstrument = structlog.get_config()["processors"]
        has_otel = any(
            isinstance(p, OpenTelemetryProcessor) for p in config_after_uninstrument
        )
        self.assertFalse(has_otel)

    def test_double_instrument_prevented(self):
        """Test that double instrumentation is prevented by BaseInstrumentor."""
        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer(),
            ]
        )

        # First instrumentation
        StructlogInstrumentor().instrument(logger_provider=self.logger_provider)
        config_after_first = structlog.get_config()["processors"]
        count_after_first = len(config_after_first)

        # Second instrumentation (should be no-op)
        StructlogInstrumentor().instrument(logger_provider=self.logger_provider)
        config_after_second = structlog.get_config()["processors"]
        count_after_second = len(config_after_second)

        # Should have same number of processors
        self.assertEqual(count_after_first, count_after_second)

    def test_custom_logger_provider(self):
        """Test that custom logger_provider is passed to the processor."""
        custom_provider = LoggerProvider()
        custom_exporter = InMemoryLogRecordExporter()
        custom_provider.add_log_record_processor(
            LoggingHandler(
                level=0,
                logger_provider=custom_provider,
            )
        )

        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer(),
            ]
        )

        # Instrument with custom provider
        StructlogInstrumentor().instrument(logger_provider=custom_provider)

        # Log something
        logger = structlog.get_logger()
        logger.info("test message")

        # Verify it went to the custom exporter
        logs = custom_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].log_record.body, "test message")

    def test_instrumentation_dependencies(self):
        """Test that instrumentation_dependencies returns the correct value."""
        instrumentor = StructlogInstrumentor()
        deps = instrumentor.instrumentation_dependencies()
        self.assertIn("structlog", " ".join(deps))
