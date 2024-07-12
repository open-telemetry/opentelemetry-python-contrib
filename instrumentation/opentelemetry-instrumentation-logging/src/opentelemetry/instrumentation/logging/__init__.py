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

# pylint: disable=empty-docstring,no-value-for-parameter,no-member,no-name-in-module

import logging  # pylint: disable=import-self
from itertools import chain
from os import environ
from typing import Collection

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.logging.constants import (
    _MODULE_DOC,
    DEFAULT_LOGGING_FORMAT,
)
from opentelemetry.instrumentation.logging.environment_variables import (
    OTEL_PYTHON_LOG_CORRELATION,
    OTEL_PYTHON_LOG_FORMAT,
    OTEL_PYTHON_LOG_LEVEL,
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED,
)
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.logging.package import _instruments
from opentelemetry.trace import (
    INVALID_SPAN,
    INVALID_SPAN_CONTEXT,
    get_current_span,
    get_tracer_provider,
)

__doc__ = _MODULE_DOC

LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


class LoggingInstrumentor(BaseInstrumentor):  # pylint: disable=empty-docstring
    __doc__ = f"""An instrumentor for stdlib logging module.

    This instrumentor injects tracing context into logging records and optionally sets the global logging format to the following:

    .. code-block::

        {DEFAULT_LOGGING_FORMAT}

        def log_hook(span: Span, record: LogRecord):
                if span and span.is_recording():
                    record.custom_user_attribute_from_log_hook = "some-value"

    Args:
        tracer_provider: Tracer provider instance that can be used to fetch a tracer.
        set_logging_format: When set to True, it calls logging.basicConfig() and sets a logging format.
        logging_format: Accepts a string and sets it as the logging format when set_logging_format
            is set to True.
        log_level: Accepts one of the following values and sets the logging level to it.
            logging.INFO
            logging.DEBUG
            logging.WARN
            logging.ERROR
            logging.FATAL
        log_hook: execute custom logic when record is created

    See `BaseInstrumentor`
    """

    _old_factory = None
    _log_hook = None
    _instrumented_loggers = None
    _instrumented_root_logger_handler = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        provider = kwargs.get("tracer_provider", None) or get_tracer_provider()
        old_factory = logging.getLogRecordFactory()
        LoggingInstrumentor._old_factory = old_factory
        LoggingInstrumentor._log_hook = kwargs.get("log_hook", None)

        service_name = None

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)

            record.otelSpanID = "0"
            record.otelTraceID = "0"
            record.otelTraceSampled = False

            nonlocal service_name
            if service_name is None:
                resource = getattr(provider, "resource", None)
                if resource:
                    service_name = (
                        resource.attributes.get("service.name") or ""
                    )
                else:
                    service_name = ""

            record.otelServiceName = service_name

            span = get_current_span()
            if span != INVALID_SPAN:
                ctx = span.get_span_context()
                if ctx != INVALID_SPAN_CONTEXT:
                    record.otelSpanID = format(ctx.span_id, "016x")
                    record.otelTraceID = format(ctx.trace_id, "032x")
                    record.otelTraceSampled = ctx.trace_flags.sampled
                    if callable(LoggingInstrumentor._log_hook):
                        try:
                            LoggingInstrumentor._log_hook(  # pylint: disable=E1102
                                span, record
                            )
                        except Exception:  # pylint: disable=W0703
                            pass

            return record

        logging.setLogRecordFactory(record_factory)
        self._instrument_loggers(**kwargs)

        set_logging_format = kwargs.get(
            "set_logging_format",
            environ.get(OTEL_PYTHON_LOG_CORRELATION, "false").lower()
            == "true",
        )

        if set_logging_format:
            log_format = kwargs.get(
                "logging_format", environ.get(OTEL_PYTHON_LOG_FORMAT, None)
            )
            log_format = log_format or DEFAULT_LOGGING_FORMAT

            log_level = kwargs.get(
                "log_level", LEVELS.get(environ.get(OTEL_PYTHON_LOG_LEVEL))
            )
            log_level = log_level or logging.INFO

            logging.basicConfig(format=log_format, level=log_level)

    @staticmethod
    def _instrument_loggers(**kwargs):
        def get_propagate(logger) -> bool:
            return logger._otel_propagate

        def set_propagate(logger, value):
            old_value = True
            try:
                old_value = logger._otel_propagate
            except AttributeError:
                pass

            if old_value != value:
                if value:
                    old_otel_handler = None
                    try:
                        old_otel_handler = logger._otel_handler
                    except AttributeError:
                        pass
                    if old_otel_handler is not None:
                        logger.removeHandler(old_otel_handler)
                    logger._otel_handler = None
                else:
                    # If the handler is already there, skip instrumentation
                    if any(
                        (
                            isinstance(handler, LoggingHandler)
                            for handler in logger.handlers
                        )
                    ):
                        logger._otel_handler = None
                    else:
                        logger._otel_handler = LoggingHandler()
                        logger.addHandler(logger._otel_handler)
            logger._otel_propagate = value

        logging_enabled = kwargs.get(
            "logging_enabled",
            environ.get(
                OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED, "false"
            ).lower()
            == "true",
        )

        if logging_enabled:
            root_logger = logging.getLogger()
            # Root logger has LoggingHandler independently on the propagate value
            if not any(
                (
                    isinstance(handler, LoggingHandler)
                    for handler in root_logger.handlers
                )
            ):
                root_logging_handler = LoggingHandler()
                root_logger.addHandler(root_logging_handler)
                LoggingInstrumentor._instrumented_root_logger_handler = (
                    root_logging_handler
                )

            for instrument_logger in chain(
                (root_logger,),
                (
                    logging.getLogger(name)
                    for name in logging.root.manager.loggerDict
                ),
            ):
                if not isinstance(instrument_logger, logging.Logger):
                    continue
                # Set the _otel_propagate attribute and install handler if necessary
                set_propagate(instrument_logger, instrument_logger.propagate)
                del instrument_logger.propagate

            logging.Logger.propagate = property(get_propagate, set_propagate)
            LoggingInstrumentor._instrumented_loggers = True

    def _uninstrument(self, **kwargs):
        self._uninstrument_loggers()
        if LoggingInstrumentor._old_factory:
            logging.setLogRecordFactory(LoggingInstrumentor._old_factory)
            LoggingInstrumentor._old_factory = None

    @staticmethod
    def _uninstrument_loggers():
        if LoggingInstrumentor._instrumented_loggers:
            LoggingInstrumentor._instrumented_loggers = False

            root_logger = logging.getLogger()

            if (
                LoggingInstrumentor._instrumented_root_logger_handler
                is not None
            ):
                root_logger.removeHandler(
                    LoggingInstrumentor._instrumented_root_logger_handler
                )
                LoggingInstrumentor._instrumented_root_logger_handler = None

            del logging.Logger.propagate

            for uninstrument_logger in chain(
                (root_logger,),
                (
                    logging.getLogger(name)
                    for name in logging.root.manager.loggerDict
                ),
            ):
                if not isinstance(uninstrument_logger, logging.Logger):
                    continue

                if hasattr(uninstrument_logger, "_otel_propagate"):
                    uninstrument_logger.propagate = (
                        uninstrument_logger._otel_propagate
                    )
                    del uninstrument_logger._otel_propagate
                if hasattr(uninstrument_logger, "_otel_handler"):
                    if uninstrument_logger._otel_handler is not None:
                        uninstrument_logger.removeHandler(
                            uninstrument_logger._otel_handler
                        )
                    del uninstrument_logger._otel_handler
