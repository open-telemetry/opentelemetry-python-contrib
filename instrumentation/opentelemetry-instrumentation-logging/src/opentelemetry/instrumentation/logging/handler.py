# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import logging.config
import threading
import traceback
from contextvars import ContextVar
from time import time_ns
from typing import Callable, Mapping

from opentelemetry._logs import (
    LoggerProvider,
    LogRecord,
    NoOpLogger,
    get_logger,
    get_logger_provider,
)
from opentelemetry.context import get_current
from opentelemetry.instrumentation.log_utils import std_to_otel
from opentelemetry.semconv._incubating.attributes import code_attributes
from opentelemetry.semconv.attributes import exception_attributes
from opentelemetry.util.types import AnyValue

_internal_logger = logging.getLogger(__name__ + ".internal")
_internal_logger.propagate = False
_internal_logger.addHandler(logging.StreamHandler())


_OTEL_PYTHON_LOG_HANDLER_LEVEL_BY_NAME = {
    "notset": logging.NOTSET,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _setup_logging_handler(
    logger_provider: LoggerProvider,
    log_code_attributes: bool = False,
    level: int | None = None,
) -> LoggingHandler:
    handler = LoggingHandler(
        level=level or logging.NOTSET,
        logger_provider=logger_provider,
        log_code_attributes=log_code_attributes,
    )
    logging.getLogger().addHandler(handler)
    _overwrite_logging_config_fns(handler)
    return handler


def _overwrite_logging_config_fns(handler: "LoggingHandler") -> None:
    root = logging.getLogger()

    def wrapper(config_fn: Callable) -> Callable:
        def overwritten_config_fn(*args, **kwargs):
            removed_handler = False
            # We don't want the OTLP handler to be modified or deleted by the logging config functions.
            # So we remove it and then add it back after the function call.
            if handler in root.handlers:
                removed_handler = True
                root.handlers.remove(handler)
            try:
                config_fn(*args, **kwargs)
            finally:
                # Ensure handler is added back if logging function throws exception.
                if removed_handler:
                    root.addHandler(handler)

        return overwritten_config_fn

    logging.config.fileConfig = wrapper(logging.config.fileConfig)
    logging.config.dictConfig = wrapper(logging.config.dictConfig)
    logging.basicConfig = wrapper(logging.basicConfig)


# skip natural LogRecord attributes
# http://docs.python.org/library/logging.html#logrecord-attributes
_RESERVED_ATTRS = frozenset(
    (
        "asctime",
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "getMessage",
        "message",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    )
)


class LoggingHandler(logging.Handler):
    """A handler class which writes logging records, in OTLP format, to
    a network destination or file. Supports signals from the `logging` module.
    https://docs.python.org/3/library/logging.html
    """

    _is_emitting: ContextVar[bool] = ContextVar("_is_emitting", default=False)

    def __init__(
        self,
        level: int = logging.NOTSET,
        logger_provider: LoggerProvider | None = None,
        log_code_attributes: bool = False,
    ) -> None:
        super().__init__(level=level)
        self._logger_provider = logger_provider or get_logger_provider()

        self._log_code_attributes = log_code_attributes

    def _get_attributes(
        self, record: logging.LogRecord
    ) -> Mapping[str, AnyValue]:
        attributes = {
            k: v for k, v in vars(record).items() if k not in _RESERVED_ATTRS
        }

        if self._log_code_attributes:
            # Add standard code attributes for logs.
            attributes[code_attributes.CODE_FILE_PATH] = record.pathname
            attributes[code_attributes.CODE_FUNCTION_NAME] = record.funcName
            attributes[code_attributes.CODE_LINE_NUMBER] = record.lineno

        if record.exc_info:
            exctype, value, tb = record.exc_info
            if exctype is not None:
                attributes[exception_attributes.EXCEPTION_TYPE] = (
                    exctype.__name__
                )
            if value is not None and value.args:
                attributes[exception_attributes.EXCEPTION_MESSAGE] = str(
                    value.args[0]
                )
            if tb is not None:
                # https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/#stacktrace-representation
                attributes[exception_attributes.EXCEPTION_STACKTRACE] = (
                    "".join(traceback.format_exception(*record.exc_info))
                )
        return attributes

    def _translate(self, record: logging.LogRecord) -> LogRecord:
        timestamp = int(record.created * 1e9)
        observered_timestamp = time_ns()
        attributes = self._get_attributes(record)
        severity_number = std_to_otel(record.levelno)
        if self.formatter:
            body = self.format(record)
        else:
            body = record.getMessage()

        # Map Python log level names to OTel severity text as defined in
        # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/logs/data-model.md#displaying-severity
        _python_to_otel_severity_text = {
            "WARNING": "WARN",
            "CRITICAL": "FATAL",
        }
        level_name = _python_to_otel_severity_text.get(
            record.levelname, record.levelname
        )

        return LogRecord(
            timestamp=timestamp,
            observed_timestamp=observered_timestamp,
            context=get_current() or None,
            severity_text=level_name,
            severity_number=severity_number,
            body=body,
            attributes=attributes,
        )

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a record. Skip emitting if logger is NoOp.

        The record is translated to OTel format, and then sent across the pipeline.
        """
        # Prevent recursive logging that can cause infinite recursion or deadlock.
        # During _translate(), internal OTel code (e.g., _clean_extended_attribute)
        # may call _logger.warning() for invalid attributes. If the OTel
        # LoggingHandler is in the logger chain, this warning re-enters emit(),
        # creating an infinite loop that prevents the handler lock from ever
        # being released, blocking all other threads.
        # See: https://github.com/open-telemetry/opentelemetry-python/issues/3858

        if self._is_emitting.get():
            _internal_logger.warning(
                "LoggingHandler.emit detected recursive logging, skipping to prevent deadlock."
            )
            return
        token = self._is_emitting.set(True)
        try:
            logger = get_logger(
                record.name, logger_provider=self._logger_provider
            )
            if not isinstance(logger, NoOpLogger):
                logger.emit(self._translate(record))
        finally:
            self._is_emitting.reset(token)

    def flush(self) -> None:
        """
        Flushes the logging output. Skip flushing if logging_provider has no force_flush method.
        """
        if hasattr(self._logger_provider, "force_flush") and callable(
            self._logger_provider.force_flush  # type: ignore[reportAttributeAccessIssue]
        ):
            # This is done in a separate thread to avoid a potential deadlock, for
            # details see https://github.com/open-telemetry/opentelemetry-python/pull/4636.
            thread = threading.Thread(target=self._logger_provider.force_flush)  # type: ignore[reportAttributeAccessIssue]
            thread.start()
