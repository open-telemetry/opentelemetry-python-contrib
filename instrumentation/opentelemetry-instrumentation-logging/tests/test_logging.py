# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from unittest import mock

import pytest

from opentelemetry._logs import get_logger_provider
from opentelemetry.instrumentation.logging import (
    DEFAULT_LOGGING_FORMAT,
    LoggingInstrumentor,
)
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import INVALID_SPAN, NoOpTracerProvider, ProxyTracer, get_tracer


class FakeTracerProvider:
    def get_tracer(  # pylint: disable=no-self-use
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
    ) -> ProxyTracer:
        return ProxyTracer(
            instrumenting_module_name,
            instrumenting_library_version,
            schema_url,
        )


# pylint: disable=no-self-use,too-many-public-methods
class TestLoggingInstrumentorProxyTracerProvider(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog

    def setUp(self):
        super().setUp()
        LoggingInstrumentor().instrument(tracer_provider=FakeTracerProvider(), set_logging_format=True)

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
        self.caplog = caplog

    def setUp(self):
        super().setUp()
        LoggingInstrumentor().instrument()
        self.tracer = get_tracer(__name__)

    def tearDown(self):
        super().tearDown()
        LoggingInstrumentor().uninstrument()

    def assert_trace_context_injected(self, span_id, trace_id, trace_sampled, resource_attributes):
        with self.caplog.at_level(level=logging.INFO):
            logger = logging.getLogger("test logger")
            logger.info("hello")
            self.assertEqual(len(self.caplog.records), 1)
            record = self.caplog.records[0]
            self.assertEqual(record.otelSpanID, span_id)
            self.assertEqual(record.otelTraceID, trace_id)
            self.assertEqual(record.otelTraceSampled, trace_sampled)
            self.assertEqual(record.otelServiceName, resource_attributes["service.name"])

    @mock.patch.dict("os.environ", {"OTEL_PYTHON_LOG_CORRELATION": "true"})
    @mock.patch("logging.basicConfig")
    def test_trace_context_injection_with_log_correlation_from_env_var(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        basic_config_mock.assert_called_once_with(format=DEFAULT_LOGGING_FORMAT, level=logging.INFO)
        with self.tracer.start_as_current_span("s1") as span:
            span_ctx = span.get_span_context()
            span_id = format(span_ctx.span_id, "016x")
            trace_id = format(span_ctx.trace_id, "032x")
            trace_sampled = span_ctx.trace_flags.sampled
            self.assert_trace_context_injected(span_id, trace_id, trace_sampled, span.resource.attributes)

    @mock.patch("logging.basicConfig")
    def test_trace_context_injection_with_log_correlation_instrument_arg(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(set_logging_format=True)
        basic_config_mock.assert_called_once_with(format=DEFAULT_LOGGING_FORMAT, level=logging.INFO)
        with self.tracer.start_as_current_span("s1") as span:
            span_ctx = span.get_span_context()
            span_id = format(span_ctx.span_id, "016x")
            trace_id = format(span_ctx.trace_id, "032x")
            trace_sampled = span_ctx.trace_flags.sampled
            self.assert_trace_context_injected(span_id, trace_id, trace_sampled, span.resource.attributes)

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

    @mock.patch("logging.basicConfig")
    def test_inject_trace_context_arg(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(inject_trace_context=True)
        basic_config_mock.assert_not_called()
        with self.tracer.start_as_current_span("s1") as span:
            span_ctx = span.get_span_context()
            span_id = format(span_ctx.span_id, "016x")
            trace_id = format(span_ctx.trace_id, "032x")
            trace_sampled = span_ctx.trace_flags.sampled
            self.assert_trace_context_injected(span_id, trace_id, trace_sampled, span.resource.attributes)

    @mock.patch("logging.basicConfig")
    def test_inject_trace_context_arg_without_span(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(inject_trace_context=True)
        basic_config_mock.assert_not_called()
        self.assert_trace_context_injected("0", "0", False, self.tracer.resource.attributes)

    @mock.patch("logging.basicConfig")
    def test_trace_context_injection_without_span(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(set_logging_format=True)
        basic_config_mock.assert_called_once_with(format=DEFAULT_LOGGING_FORMAT, level=logging.INFO)
        self.assert_trace_context_injected("0", "0", False, self.tracer.resource.attributes)

    @mock.patch("logging.basicConfig")
    def test_basic_config_called(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument()
        self.assertFalse(basic_config_mock.called)
        LoggingInstrumentor().uninstrument()

        with mock.patch.dict("os.environ", {"OTEL_PYTHON_LOG_CORRELATION": "true"}):
            LoggingInstrumentor().instrument()
            basic_config_mock.assert_called_with(format=DEFAULT_LOGGING_FORMAT, level=logging.INFO)

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
            basic_config_mock.assert_called_with(format="%(message)s %(otelSpanID)s", level=logging.ERROR)

    @mock.patch("logging.basicConfig")
    def test_custom_format_and_level_api(self, basic_config_mock):  # pylint: disable=no-self-use
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(
            set_logging_format=True,
            logging_format="%(message)s span_id=%(otelSpanID)s",
            log_level=logging.WARNING,
        )
        basic_config_mock.assert_called_with(format="%(message)s span_id=%(otelSpanID)s", level=logging.WARNING)

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
                self.assertEqual(record.custom_user_attribute_from_log_hook, "some-value")

    def test_log_hook_without_span(self):
        LoggingInstrumentor().uninstrument()
        hook = mock.Mock()
        LoggingInstrumentor().instrument(log_hook=hook)

        with self.caplog.at_level(level=logging.INFO):
            logger = logging.getLogger("test logger")
            logger.info("hello")

        self.assertEqual(len(self.caplog.records), 1)
        hook.assert_called_once_with(INVALID_SPAN, self.caplog.records[0])

    @mock.patch("logging.basicConfig")
    def test_log_hook_with_set_logging_format(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(
            set_logging_format=True,
            log_hook=log_hook,
        )
        basic_config_mock.assert_called_once_with(format=DEFAULT_LOGGING_FORMAT, level=logging.INFO)
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
                self.assertEqual(record.otelServiceName, span.resource.attributes["service.name"])
                self.assertEqual(record.otelTraceSampled, trace_sampled)
                self.assertEqual(record.custom_user_attribute_from_log_hook, "some-value")

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

        root_logger = logging.getLogger()
        logging_handler_instances = [handler for handler in root_logger.handlers if isinstance(handler, LoggingHandler)]
        self.assertEqual(logging_handler_instances, [])

    def test_uninstrument_after_set_logging_format_allows_further_logging(self):
        LoggingInstrumentor().uninstrument()
        root_logger = logging.getLogger()
        # Save existing handlers to restore after test
        orig_handlers = list(root_logger.handlers)

        try:
            LoggingInstrumentor().instrument(set_logging_format=True)
            logger = logging.getLogger("test_uninstrument_logging")
            with self.caplog.at_level(level=logging.INFO):
                logger.info("while instrumented")
                self.assertEqual(len(self.caplog.records), 1)
                self.assertTrue(hasattr(self.caplog.records[0], "otelTraceID"))

            LoggingInstrumentor().uninstrument()

            # Logging after uninstrument should succeed without KeyError / ValueError on formatting
            with self.caplog.at_level(level=logging.INFO):
                logger.info("after uninstrument")
                self.assertEqual(len(self.caplog.records), 2)
                # Ensure the new log record does not have otelTraceID and formats cleanly
                after_record = self.caplog.records[1]
                self.assertFalse(hasattr(after_record, "otelTraceID"))
                # Format with all active root handlers should not raise
                for handler in root_logger.handlers:
                    if handler.formatter:
                        formatted = handler.format(after_record)
                        self.assertIn("after uninstrument", formatted)
        finally:
            LoggingInstrumentor().uninstrument()
            root_logger.handlers = orig_handlers

    def test_uninstrument_removes_only_handlers_added_by_basicconfig(self):
        LoggingInstrumentor().uninstrument()
        root_logger = logging.getLogger()
        orig_handlers = list(root_logger.handlers)
        orig_level = root_logger.level

        custom_handler = logging.StreamHandler()
        custom_formatter = logging.Formatter("CUSTOM: %(message)s")
        custom_handler.setFormatter(custom_formatter)

        try:
            # Start from a handler-less root so that basicConfig actually runs
            # (it only adds a handler when the root logger has no handlers).
            root_logger.handlers = []

            LoggingInstrumentor().instrument(set_logging_format=True)

            # basicConfig ran: it added a StreamHandler and set the root level.
            basic_config_handlers = [h for h in root_logger.handlers if not isinstance(h, LoggingHandler)]
            self.assertEqual(len(basic_config_handlers), 1)
            self.assertEqual(root_logger.level, logging.INFO)

            # A handler the application adds while instrumented must survive
            # uninstrument (regression: uninstrument used to drop it).
            root_logger.addHandler(custom_handler)

            LoggingInstrumentor().uninstrument()

            self.assertNotIn(basic_config_handlers[0], root_logger.handlers)
            self.assertIn(custom_handler, root_logger.handlers)
            self.assertEqual(custom_handler.formatter, custom_formatter)
            self.assertEqual(root_logger.level, orig_level)

            record = root_logger.makeRecord("test", logging.INFO, "test.py", 1, "restored message", (), None)
            formatted = custom_handler.format(record)
            self.assertEqual(formatted, "CUSTOM: restored message")
        finally:
            LoggingInstrumentor().uninstrument()
            if custom_handler in root_logger.handlers:
                root_logger.removeHandler(custom_handler)
            root_logger.handlers = orig_handlers
            root_logger.setLevel(orig_level)

    def test_uninstrument_preserves_level_changed_by_application(self):
        LoggingInstrumentor().uninstrument()
        root_logger = logging.getLogger()
        orig_handlers = list(root_logger.handlers)
        orig_level = root_logger.level

        try:
            root_logger.handlers = []
            root_logger.setLevel(logging.WARNING)

            LoggingInstrumentor().instrument(set_logging_format=True)
            self.assertEqual(root_logger.level, logging.INFO)

            root_logger.setLevel(logging.ERROR)
            LoggingInstrumentor().uninstrument()

            self.assertEqual(root_logger.level, logging.ERROR)
        finally:
            LoggingInstrumentor().uninstrument()
            root_logger.handlers = orig_handlers
            root_logger.setLevel(orig_level)

    def test_uninstrument_does_not_restore_level_when_basicconfig_is_no_op(self):
        LoggingInstrumentor().uninstrument()
        root_logger = logging.getLogger()
        orig_handlers = list(root_logger.handlers)
        orig_level = root_logger.level
        custom_handler = logging.StreamHandler()

        try:
            root_logger.handlers = [custom_handler]
            root_logger.setLevel(logging.WARNING)

            LoggingInstrumentor().instrument(set_logging_format=True)
            root_logger.setLevel(logging.ERROR)
            LoggingInstrumentor().uninstrument()

            self.assertEqual(root_logger.level, logging.ERROR)
            self.assertIn(custom_handler, root_logger.handlers)
        finally:
            LoggingInstrumentor().uninstrument()
            root_logger.handlers = orig_handlers
            root_logger.setLevel(orig_level)

    def test_uninstrument_stops_the_orphaned_factory_injecting(self):
        # The factory cannot be unlinked from the middle of the chain, so
        # uninstrument has to neutralise it in place: records built afterwards
        # must carry no OTel attributes.
        LoggingInstrumentor().uninstrument()
        baseline = logging.getLogRecordFactory()
        LoggingInstrumentor().instrument(inject_trace_context=True)
        chained_onto = logging.getLogRecordFactory()

        def app_factory(*args, **kwargs):
            return chained_onto(*args, **kwargs)

        logging.setLogRecordFactory(app_factory)
        try:
            record = logging.getLogRecordFactory()("n", logging.INFO, "p", 1, "m", None, None)
            self.assertTrue(hasattr(record, "otelTraceID"))

            LoggingInstrumentor().uninstrument()

            self.assertIs(logging.getLogRecordFactory(), app_factory)
            record = logging.getLogRecordFactory()("n", logging.INFO, "p", 1, "m", None, None)
            self.assertFalse(hasattr(record, "otelServiceName"))
            self.assertFalse(hasattr(record, "otelSpanID"))
            self.assertFalse(hasattr(record, "otelTraceID"))
            self.assertFalse(hasattr(record, "otelTraceSampled"))
        finally:
            logging.setLogRecordFactory(baseline)

    def test_uninstrument_stops_the_orphaned_factory_calling_the_log_hook(self):
        # The log hook is the other way the orphan can keep mutating records,
        # and it runs on a different branch of record_factory than the context
        # injection above.
        LoggingInstrumentor().uninstrument()
        baseline = logging.getLogRecordFactory()
        calls = []
        LoggingInstrumentor().instrument(log_hook=lambda span, record: calls.append(record))
        chained_onto = logging.getLogRecordFactory()

        def app_factory(*args, **kwargs):
            return chained_onto(*args, **kwargs)

        logging.setLogRecordFactory(app_factory)
        try:
            with self.tracer.start_as_current_span("s1"):
                logging.getLogRecordFactory()("n", logging.INFO, "p", 1, "m", None, None)
                self.assertEqual(len(calls), 1)

                LoggingInstrumentor().uninstrument()

                logging.getLogRecordFactory()("n", logging.INFO, "p", 1, "m", None, None)
                self.assertEqual(len(calls), 1)
        finally:
            logging.setLogRecordFactory(baseline)

    def test_reinstrument_disables_an_orphan_left_by_an_earlier_instrument(self):
        # _our_factory is class state, so re-instrumenting rebinds it to the new
        # wrapper and the orphan stranded by the previous cycle must stay
        # disabled. Reaching past the new head is the only way to observe that:
        # injection is idempotent, so a doubled pass looks identical from above.
        LoggingInstrumentor().uninstrument()
        baseline = logging.getLogRecordFactory()
        LoggingInstrumentor().instrument(inject_trace_context=True)
        orphan = logging.getLogRecordFactory()

        def app_factory(*args, **kwargs):
            return orphan(*args, **kwargs)

        logging.setLogRecordFactory(app_factory)
        try:
            LoggingInstrumentor().uninstrument()
            LoggingInstrumentor().instrument(inject_trace_context=True)

            record = logging.getLogRecordFactory()("n", logging.INFO, "p", 1, "m", None, None)
            self.assertTrue(hasattr(record, "otelTraceID"))

            record = app_factory("n", logging.INFO, "p", 1, "m", None, None)
            self.assertFalse(hasattr(record, "otelTraceID"))
        finally:
            LoggingInstrumentor().uninstrument()
            logging.setLogRecordFactory(baseline)

    def test_uninstrument_keeps_factories_chained_after_ours(self):
        # A factory installed after ours must survive uninstrument: the
        # logging module offers no way to unlink a factory from the middle of
        # the chain, so restoring the old factory here would silently drop it.
        LoggingInstrumentor().uninstrument()
        baseline = logging.getLogRecordFactory()
        LoggingInstrumentor().instrument()
        chained_onto = logging.getLogRecordFactory()

        def app_factory(*args, **kwargs):
            record = chained_onto(*args, **kwargs)
            record.custom_app_attribute = "some-value"
            return record

        logging.setLogRecordFactory(app_factory)
        try:
            LoggingInstrumentor().uninstrument()

            self.assertIs(logging.getLogRecordFactory(), app_factory)
            with self.caplog.at_level(level=logging.INFO):
                logging.getLogger("test logger").info("hello")
                records = [record for record in self.caplog.records if record.name == "test logger"]
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].custom_app_attribute, "some-value")
        finally:
            logging.setLogRecordFactory(baseline)

    def test_uninstrument_restores_factory_when_nothing_chained(self):
        # Observe the pre-instrumentation factory rather than reading it back
        # out of LoggingInstrumentor._old_factory: sourcing the expected value
        # from the code under test would let this pass vacuously if that
        # attribute were ever None. setUp() has already instrumented, so unwind
        # once before taking the reading.
        LoggingInstrumentor().uninstrument()
        original_factory = logging.getLogRecordFactory()

        LoggingInstrumentor().instrument()
        self.assertIsNot(logging.getLogRecordFactory(), original_factory)

        LoggingInstrumentor().uninstrument()
        self.assertIs(logging.getLogRecordFactory(), original_factory)

    @mock.patch("logging.basicConfig")
    def test_no_op_tracer_provider(self, basic_config_mock):
        LoggingInstrumentor().uninstrument()
        LoggingInstrumentor().instrument(tracer_provider=NoOpTracerProvider(), set_logging_format=True)
        basic_config_mock.assert_called_once_with(format=DEFAULT_LOGGING_FORMAT, level=logging.INFO)

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
    def test_handler_setup_is_disabled_if_sdk_autoinstrumentation_env_var_is_set_to_true(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        self.assertEqual(len(self.caplog.records), 1)
        record = self.caplog.records[0]
        self.assertEqual(
            record.message,
            "Skipping installation of LoggingHandler from `opentelemetry-instrumentation-logging` "
            "to avoid duplicate logs. The SDK's deprecated LoggingHandler is already "
            "active (OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true). To migrate, unset "
            "this environment variable. The SDK's handler will be removed in a future release.",
        )

        root_logger = logging.getLogger()
        logging_handler_instances = [handler for handler in root_logger.handlers if isinstance(handler, LoggingHandler)]
        self.assertEqual(logging_handler_instances, [])

    @mock.patch.dict(
        "os.environ",
        {"OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED": "false"},
    )
    def test_handler_setup_is_enabled_if_sdk_autoinstrumentation_env_var_is_set_to_false(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        self.assertEqual(len(self.caplog.records), 0)
        root_logger = logging.getLogger()
        logging_handler_instances = [handler for handler in root_logger.handlers if isinstance(handler, LoggingHandler)]
        self.assertEqual(len(logging_handler_instances), 1)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION": "false"},
    )
    def test_handler_setup_is_enabled_if_autoinstrumentation_env_var_is_set_to_false(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        self.assertEqual(len(self.caplog.records), 0)
        root_logger = logging.getLogger()
        logging_handler_instances = [handler for handler in root_logger.handlers if isinstance(handler, LoggingHandler)]
        self.assertEqual(logging_handler_instances, [])

    def test_handler_setup_is_called_if_autoinstrumentation_env_vars_are_not_set(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        self.assertEqual(len(self.caplog.records), 0)
        root_logger = logging.getLogger()
        logging_handler_instances = [handler for handler in root_logger.handlers if isinstance(handler, LoggingHandler)]
        self.assertEqual(len(logging_handler_instances), 1)

    def test_handler_setup_is_called_without_code_attributes_by_default(self):
        LoggingInstrumentor().uninstrument()
        with mock.patch("opentelemetry.instrumentation.logging._setup_logging_handler") as setup_mock:
            LoggingInstrumentor().instrument()

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider,
            log_code_attributes=False,
            level=None,
        )

    @mock.patch.dict("os.environ", {"OTEL_PYTHON_LOG_CODE_ATTRIBUTES": "true"})
    def test_handler_setup_is_called_with_code_attributes_from_env_var(self):
        LoggingInstrumentor().uninstrument()
        with mock.patch("opentelemetry.instrumentation.logging._setup_logging_handler") as setup_mock:
            LoggingInstrumentor().instrument()

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider,
            log_code_attributes=True,
            level=None,
        )

    def test_handler_setup_is_controlled_by_instrumentor_parameter(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument(enable_log_auto_instrumentation=False)

        self.assertEqual(len(self.caplog.records), 0)
        root_logger = logging.getLogger()
        logging_handler_instances = [handler for handler in root_logger.handlers if isinstance(handler, LoggingHandler)]
        self.assertEqual(logging_handler_instances, [])

    def test_handler_code_attributes_is_controlled_by_instrumentor_parameter(
        self,
    ):
        LoggingInstrumentor().uninstrument()
        with mock.patch("opentelemetry.instrumentation.logging._setup_logging_handler") as setup_mock:
            LoggingInstrumentor().instrument(log_code_attributes=True)

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider,
            log_code_attributes=True,
            level=None,
        )

    @mock.patch.dict("os.environ", {"OTEL_PYTHON_LOG_HANDLER_LEVEL": "error"})
    def test_handler_level_is_set_from_env_var(self):
        LoggingInstrumentor().uninstrument()
        with self.caplog.at_level(level=logging.WARNING):
            LoggingInstrumentor().instrument()

        root_logger = logging.getLogger()
        logging_handlers = [h for h in root_logger.handlers if isinstance(h, LoggingHandler)]
        self.assertEqual(len(logging_handlers), 1)
        self.assertEqual(logging_handlers[0].level, logging.ERROR)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_PYTHON_LOG_HANDLER_LEVEL": "warning"},
    )
    def test_handler_setup_called_with_level_from_env_var(self):
        LoggingInstrumentor().uninstrument()
        with mock.patch("opentelemetry.instrumentation.logging._setup_logging_handler") as setup_mock:
            LoggingInstrumentor().instrument()

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider,
            log_code_attributes=False,
            level=logging.WARNING,
        )

    def test_handler_level_is_controlled_by_instrumentor_parameter(self):
        LoggingInstrumentor().uninstrument()
        with mock.patch("opentelemetry.instrumentation.logging._setup_logging_handler") as setup_mock:
            LoggingInstrumentor().instrument(log_handler_level=logging.DEBUG)

        logger_provider = get_logger_provider()
        setup_mock.assert_called_once_with(
            logger_provider=logger_provider,
            log_code_attributes=False,
            level=logging.DEBUG,
        )
