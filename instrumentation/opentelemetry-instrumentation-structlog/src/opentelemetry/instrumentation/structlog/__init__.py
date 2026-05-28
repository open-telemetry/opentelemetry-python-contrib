# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
The OpenTelemetry structlog integration provides a processor that emits structlog
events as OpenTelemetry logs.

.. code-block:: python

    import structlog
    from opentelemetry.instrumentation.structlog import StructlogInstrumentor

    StructlogInstrumentor().instrument()

    logger = structlog.get_logger()
    logger.info("user logged in", user_id=42)

This will emit the structlog event as an OpenTelemetry LogRecord, preserving all
context including trace context, custom attributes, and exception information.
"""

import sys
import traceback
from datetime import datetime
from time import time_ns
from typing import Any, Callable, Collection, Optional

import structlog

from opentelemetry._logs import (
    LogRecord,
    NoOpLogger,
    SeverityNumber,
    get_logger,
    get_logger_provider,
)
from opentelemetry.context import get_current
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.log_utils import std_to_otel
from opentelemetry.instrumentation.structlog.package import _instruments
from opentelemetry.semconv.attributes import (
    exception_attributes,
)

# Reserved keys that structlog uses internally and should not be passed as attributes
_STRUCTLOG_RESERVED_KEYS = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "exc_info",
        "exception",
        "_record",
        "_logger",
        "_name",
    }
)

# Map structlog level names to standard library log level numbers
_STRUCTLOG_LEVEL_TO_LEVELNO = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
    "fatal": 50,
}

# Map structlog level names to OTel canonical severity text where they differ
_STRUCTLOG_TO_OTEL_SEVERITY_TEXT = {
    "warning": "WARN",
    "critical": "FATAL",
    "fatal": "FATAL",
}


def _parse_structlog_timestamp(value: Any) -> Optional[int]:
    """
    Convert a structlog timestamp value to nanoseconds since epoch, or None.

    structlog's TimeStamper emits either a float (UNIX seconds, the default)
    or a string (ISO 8601 when fmt="iso", or a strftime pattern otherwise).
    We handle float and timezone-aware ISO 8601; anything else returns None so
    the SDK can fill in the observed time.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value * 1e9)
    if isinstance(value, str):
        timestamp = value
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(timestamp)
            if dt.tzinfo is None:
                return None
            return int(dt.timestamp() * 1e9)
        except ValueError:
            return None
    return None


class StructlogProcessor:
    """
    A structlog processor that translates structlog events into OpenTelemetry
    LogRecords.

    This processor should be added to the structlog processor chain to emit logs
    to OpenTelemetry. It translates structlog's event dictionary format into the
    OpenTelemetry Logs data model.

    Args:
        logger_provider: The LoggerProvider to use. If None, uses the global provider.
    """

    def __init__(self, logger_provider=None):
        """Initialize the processor with an optional logger provider."""
        self._logger_provider = logger_provider or get_logger_provider()

    def __call__(self, logger, method_name: str, event_dict: dict) -> dict:
        """
        Process a structlog event and emit it as an OpenTelemetry log.

        This method implements the structlog processor interface. It receives
        the event dictionary, translates it to an OTel LogRecord, and emits it.

        Args:
            logger: The wrapped structlog logger.
            method_name: The logger method name.
            event_dict: The structlog event dictionary.

        Returns:
            The unmodified event_dict (passthrough for other processors).
        """
        logger_name = getattr(logger, "name", __name__)
        otel_logger = get_logger(
            logger_name, logger_provider=self._logger_provider
        )

        # Skip emission if we have a no-op logger
        if not isinstance(otel_logger, NoOpLogger):
            log_record = self._translate(event_dict, method_name)
            otel_logger.emit(log_record)

        return event_dict

    @staticmethod
    def _get_attributes(event_dict: dict) -> dict[str, Any]:
        """
        Extract attributes from the structlog event dictionary.

        Filters out reserved keys and extracts exception information into
        the appropriate semantic convention attributes.

        Args:
            event_dict: The structlog event dictionary.

        Returns:
            Dictionary of attributes to attach to the LogRecord.
        """
        # Start with all non-reserved keys
        attributes = {
            k: v
            for k, v in event_dict.items()
            if k not in _STRUCTLOG_RESERVED_KEYS
        }

        # Handle exception information
        exc_info = event_dict.get("exc_info")

        # Match True explicitly because exception tuples and exception instances
        # are also truthy and are handled separately below.
        if exc_info is True:
            # exc_info=True means "get current exception"
            exc_info = sys.exc_info()
        elif isinstance(exc_info, BaseException):
            # exc_info can also be passed as an exception instance directly
            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)

        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            exctype, value, tb = exc_info
            if exctype is not None:
                attributes[exception_attributes.EXCEPTION_TYPE] = (
                    exctype.__name__
                )
            if value is not None and value.args:
                attributes[exception_attributes.EXCEPTION_MESSAGE] = str(
                    value.args[0]
                )
            if tb is not None:
                attributes[exception_attributes.EXCEPTION_STACKTRACE] = (
                    "".join(traceback.format_exception(*exc_info))
                )

        # Handle pre-rendered exception string (from structlog's ExceptionRenderer)
        exception_str = event_dict.get("exception")
        if isinstance(exception_str, str):
            # If we don't already have a stacktrace from exc_info, use this
            if exception_attributes.EXCEPTION_STACKTRACE not in attributes:
                attributes[exception_attributes.EXCEPTION_STACKTRACE] = (
                    exception_str
                )

        return attributes

    def _translate(
        self, event_dict: dict, method_name: Optional[str] = None
    ) -> LogRecord:
        """
        Translate a structlog event dictionary into an OpenTelemetry LogRecord.

        Args:
            event_dict: The structlog event dictionary.

        Returns:
            An OpenTelemetry LogRecord.
        """
        # observed_timestamp is when the SDK received the event (always now).
        # timestamp is when the event occurred; use the structlog "timestamp"
        # field if present and parseable (UNIX float or ISO 8601 string),
        # otherwise leave as None and let the SDK fill it in.
        observed_timestamp = time_ns()
        timestamp = _parse_structlog_timestamp(event_dict.get("timestamp"))

        # Get the log level and map to OTel severity. structlog passes the
        # logger method name to processors, so use it as a fallback when no
        # prior processor added a level to the event dict.
        level_str = event_dict.get("level")
        if not isinstance(level_str, str) or not level_str:
            level_str = method_name

        level_name = level_str.lower() if isinstance(level_str, str) else None
        levelno = (
            _STRUCTLOG_LEVEL_TO_LEVELNO.get(level_name)
            if level_name is not None
            else None
        )

        if levelno is None:
            severity_number = SeverityNumber.UNSPECIFIED
            severity_text = (
                level_str.upper() if isinstance(level_str, str) else None
            )
        else:
            severity_number = std_to_otel(levelno)
            # Normalize severity text to OTel canonical names where structlog
            # level names differ: "warning" -> "WARN", "critical"/"fatal" -> "FATAL"
            severity_text = _STRUCTLOG_TO_OTEL_SEVERITY_TEXT.get(
                level_name, level_str.upper()
            )

        # Get the message body
        body = event_dict.get("event")

        # Get attributes (filters reserved keys and extracts exception info)
        attributes = self._get_attributes(event_dict)

        # Get the current OTel context (includes trace context and baggage)
        context = get_current()

        return LogRecord(
            timestamp=timestamp,
            observed_timestamp=observed_timestamp,
            context=context,
            severity_text=severity_text,
            severity_number=severity_number,
            body=body,
            attributes=attributes,
        )

    def flush(self) -> None:
        """
        Flush the logger provider.
        """
        if hasattr(self._logger_provider, "force_flush") and callable(
            self._logger_provider.force_flush
        ):
            self._logger_provider.force_flush()


class StructlogInstrumentor(BaseInstrumentor):
    """
    An instrumentor for the structlog logging library.

    This instrumentor adds a StructlogProcessor to the structlog processor
    chain, enabling automatic emission of structlog events as OpenTelemetry logs.

    Example:
        >>> from opentelemetry.instrumentation.structlog import StructlogInstrumentor
        >>> import structlog
        >>> StructlogInstrumentor().instrument()
        >>> logger = structlog.get_logger()
        >>> logger.info("hello", user="alice")
    """

    _processor: Optional["StructlogProcessor"] = None
    _original_configure: Callable[..., None] = structlog.configure

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the required instrumentation dependencies."""
        return _instruments

    def _instrument(self, **kwargs):
        """
        Add the StructlogProcessor to structlog's processor chain.

        The processor is inserted before the last processor in the current chain.
        This assumes the last processor is a renderer (e.g. ConsoleRenderer,
        JSONRenderer). The processor must run before rendering so it receives the
        raw event dict rather than a formatted string.

        If your chain does not end with a renderer, or has post-processing steps
        after the renderer, configure the chain manually instead of relying on
        auto-instrumentation:

            structlog.configure(processors=[
                structlog.stdlib.add_log_level,
                StructlogProcessor(logger_provider=provider),
                structlog.dev.ConsoleRenderer(),
            ])

        Args:
            logger_provider: Optional LoggerProvider to use.
        """
        # Create the OTel processor
        logger_provider = kwargs.get("logger_provider")
        processor = StructlogProcessor(logger_provider=logger_provider)

        # Get current structlog configuration
        config = structlog.get_config()
        current_processors = list(config.get("processors", []))

        # Insert before the last processor, assumed to be the renderer.
        if current_processors:
            insert_position = len(current_processors) - 1
        else:
            insert_position = 0

        current_processors.insert(insert_position, processor)

        # Reconfigure structlog with the new processor chain
        structlog.configure(processors=current_processors)

        # Store reference for uninstrumentation
        StructlogInstrumentor._processor = processor

        # Wrap structlog.configure so that if user code calls it after
        # instrumentation, the processor is re-inserted into the new chain.
        StructlogInstrumentor._original_configure = structlog.configure

        def ensure_processor(processors):
            processors = list(processors)
            if not any(isinstance(p, StructlogProcessor) for p in processors):
                insert_position = max(len(processors) - 1, 0)
                processors.insert(
                    insert_position, StructlogInstrumentor._processor
                )
            return processors

        def patched_configure(*args, **kwargs):
            # If the user is supplying a processors list, ensure our processor
            # is included before passing it to the original configure.
            if args and "processors" not in kwargs:
                processors = args[0]
                if processors is not None:
                    args = (ensure_processor(processors), *args[1:])
            elif kwargs.get("processors") is not None:
                kwargs["processors"] = ensure_processor(kwargs["processors"])
            return StructlogInstrumentor._original_configure(*args, **kwargs)

        structlog.configure = patched_configure

    def _uninstrument(self, **kwargs):
        """
        Remove the StructlogProcessor from structlog's processor chain.
        """
        # Get current structlog configuration
        config = structlog.get_config()
        current_processors = list(config.get("processors", []))

        # Remove all StructlogProcessor instances
        new_processors = [
            p
            for p in current_processors
            if not isinstance(p, StructlogProcessor)
        ]

        # Restore the original structlog.configure before reconfiguring so
        # the patched version does not re-insert the processor.
        structlog.configure = StructlogInstrumentor._original_configure

        # Reconfigure structlog without the processor
        structlog.configure(processors=new_processors)

        # Clear reference
        StructlogInstrumentor._processor = None
