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

import pytest

from opentelemetry._logs import get_logger_provider
from opentelemetry.instrumentation.logging import (
    DEFAULT_LOGGING_FORMAT,
    LoggingInstrumentor,
)
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import NoOpTracerProvider, ProxyTracer, get_tracer


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
        LoggingInstrumentor().instrument(
            tracer_provider=FakeTracerProvider(), set_logging_format=True
        )

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

    @mock.patch.dict("os.environ", {"OTEL_PYTHON_LOG_CORRELATION": "true"})
    def test_trace_context_injection_with_log_correlation_from_env_var(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        with self.tracer.start_as_current_span("s1") as span:
            span_ctx = span.get_span_context()
            span_id = format(span_ctx.span_id, "016x")
            trace_id = format(span_ctx.trace_id, "032x")
            trace_sampled = span_ctx.trace_flags.sampled
            self.assert_trace_context_injected(
                span_id, trace_id, trace_sampled
            )

    def test_trace_context_injection_with_log_correlation_instrument_arg(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(set_logging_format=True)
        with self.tracer.start_as_current_span("s1") as span:
            span_ctx = span.get_span_context()
            span_id = format(span_ctx.span_id, "016x")
            trace_id = format(span_ctx.trace_id, "032x")
            trace_sampled = span_ctx.trace_flags.sampled
            self.assert_trace_context_injected(
                span_id, trace_id, trace_sampled
            )

    def test_no_trace_context_injection_by_default(self):
        with self.tracer.start_as_current_span("s1"):
            with self.caplog.at_level(level=logging.INFO):
                logger = logging.getLogger("test logger")
                logger.info("hello")
                self.assertEqual(len(self.caplog.records), 1)
                record = self.caplog.records[0]
                self.assertFalse(hasattr(record, "otelServiceName"))
                self.assertFalse(hasattr(record, "otelSpanID"))
                self.assertFalse(hasattr(record, "otelTraceID"))
                self.assertFalse(hasattr(record, "otelTraceSampled"))

    def test_trace_context_injection_without_span(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(set_logging_format=True)
        self.assert_trace_context_injected("0", "0", False)

    @mock.patch("logging.basicConfig")
    def test_basic_config_called(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        self.assertFalse(basic_config_mock.called)
        LoggingInstrumentor().uninstrument()

        with mock.patch.dict(
            "os.environ", {"OTEL_PYTHON_LOG_CORRELATION": "true"}
        ):
            LoggingInstrumentor().instrument()
            basic_config_mock.assert_called_with(
                format=DEFAULT_LOGGING_FORMAT, level=logging.INFO
            )

    @mock.patch("logging.basicConfig")
    def test_custom_format_and_level_env(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        self.assertFalse(basic_config_mock.called)
        LoggingInstrumentor().uninstrument()

        with mock.patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_LOG_CORRELATION": "true",
                "OTEL_PYTHON_LOG_FORMAT": "%(message)s %(otelSpanID)s",
                "OTEL_PYTHON_LOG_LEVEL": "error",
            },
        ):
            LoggingInstrumentor().instrument()
            basic_config_mock.assert_called_with(
                format="%(message)s %(otelSpanID)s", level=logging.ERROR
            )

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
            log_hook=log_hook,
        )
        with self.tracer.start_as_current_span("s1"):
            with self.caplog.at_level(level=logging.INFO):
                logger = logging.getLogger("test logger")
                logger.info("hello")
                self.assertEqual(len(self.caplog.records), 1)
                record = self.caplog.records[0]
                self.assertFalse(hasattr(record, "otelServiceName"))
                self.assertFalse(hasattr(record, "otelSpanID"))
                self.assertFalse(hasattr(record, "otelTraceID"))
                self.assertFalse(hasattr(record, "otelTraceSampled"))
                self.assertEqual(
                    record.custom_user_attribute_from_log_hook, "some-value"
                )

    def test_log_hook_with_set_logging_format(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(
            set_logging_format=True,
            log_hook=log_hook,
        )
        with self.tracer.start_as_current_span("s1") as span:
            span_ctx = span.get_span_context()
            span_id = format(span_ctx.span_id, "016x")
            trace_id = format(span_ctx.trace_id, "032x")
            trace_sampled = span_ctx.trace_flags.sampled
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
        LoggingInstrumentor().uninstrument()
        with self.tracer.start_as_current_span("s1"):
            with self.caplog.at_level(level=logging.INFO):
                logger = logging.getLogger("test logger")
                logger.info("hello")
                self.assertEqual(len(self.caplog.records), 1)
                record = self.caplog.records[0]
                self.assertFalse(hasattr(record, "otelServiceName"))
                self.assertFalse(hasattr(record, "otelSpanID"))
                self.assertFalse(hasattr(record, "otelTraceID"))
                self.assertFalse(hasattr(record, "otelTraceSampled"))

    def test_no_op_tracer_provider(self):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(
            tracer_provider=NoOpTracerProvider(), set_logging_format=True
        )

        with self.caplog.at_level(level=logging.INFO):
            logger = logging.getLogger("test logger")
            logger.info("hello")

            self.assertEqual(len(self.caplog.records), 1)
            record = self.caplog.records[0]
            self.assertEqual(record.otelSpanID, "0")
            self.assertEqual(record.otelTraceID, "0")
            self.assertEqual(record.otelServiceName, "")
            self.assertEqual(record.otelTraceSampled, False)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED": "true"},
    )
    def test_handler_setup_is_disabled_if_autoinstrumentation_env_var_is_set_to_true(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        self.assertEqual(len(self.caplog.records), 1)
        record = self.caplog.records[0]
        self.assertEqual(
            record.message,
            "Disabling logging auto-instrumentation. If you have opentelemetry-instrumentation-logging "
            "you don't need to set `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true`",
        )

        root_logger = logging.getLogger()
        logging_handler_instances = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, LoggingHandler)
        ]
        self.assertEqual(logging_handler_instances, [])

    @mock.patch.dict(
        "os.environ",
        {"OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED": "false"},
    )
    def test_handler_setup_is_disabled_if_autoinstrumentation_env_var_is_set_to_false(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        self.assertEqual(len(self.caplog.records), 0)
        root_logger = logging.getLogger()
        logging_handler_instances = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, LoggingHandler)
        ]
        self.assertEqual(logging_handler_instances, [])

    def test_handler_setup_is_called_without_code_attributes_by_default(self):
        LoggingInstrumentor().uninstrument()
        with mock.patch(
            "opentelemetry.instrumentation.logging._setup_logging_handler"
        ) as setup_mock:
            LoggingInstrumentor().instrument()

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider, log_code_attributes=False
        )

        root_logger = logging.getLogger()
        logging_handler_instances = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, LoggingHandler)
        ]
        self.assertEqual(len(logging_handler_instances), 1)

    @mock.patch.dict("os.environ", {"OTEL_PYTHON_LOG_CODE_ATTRIBUTES": "true"})
    def test_handler_setup_is_called_with_code_attributes_from_env_var(self):
        LoggingInstrumentor().uninstrument()
        with mock.patch(
            "opentelemetry.instrumentation.logging._setup_logging_handler"
        ) as setup_mock:
            LoggingInstrumentor().instrument()

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider, log_code_attributes=True
        )

        root_logger = logging.getLogger()
        logging_handler_instances = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, LoggingHandler)
        ]
        self.assertEqual(len(logging_handler_instances), 1)
