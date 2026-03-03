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
import threading
import traceback
from time import time_ns
from typing import Any, Collection

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
from opentelemetry.instrumentation.structlog.package import _instruments
from opentelemetry.semconv._incubating.attributes import (
    exception_attributes,
)

# Reserved keys that structlog uses internally and should not be passed as attributes
_STRUCTLOG_RESERVED_KEYS = frozenset({
    "event",
    "level",
    "timestamp",
    "exc_info",
    "exception",
    "_record",
    "_logger",
    "_name",
})

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

# Mapping from stdlib log levels to OTel severity numbers
# Based on the SDK's LoggingHandler implementation
_STD_TO_OTEL = {
    10: SeverityNumber.DEBUG,
    11: SeverityNumber.DEBUG2,
    12: SeverityNumber.DEBUG3,
    13: SeverityNumber.DEBUG4,
    14: SeverityNumber.DEBUG4,
    15: SeverityNumber.DEBUG4,
    16: SeverityNumber.DEBUG4,
    17: SeverityNumber.DEBUG4,
    18: SeverityNumber.DEBUG4,
    19: SeverityNumber.DEBUG4,
    20: SeverityNumber.INFO,
    21: SeverityNumber.INFO2,
    22: SeverityNumber.INFO3,
    23: SeverityNumber.INFO4,
    24: SeverityNumber.INFO4,
    25: SeverityNumber.INFO4,
    26: SeverityNumber.INFO4,
    27: SeverityNumber.INFO4,
    28: SeverityNumber.INFO4,
    29: SeverityNumber.INFO4,
    30: SeverityNumber.WARN,
    31: SeverityNumber.WARN2,
    32: SeverityNumber.WARN3,
    33: SeverityNumber.WARN4,
    34: SeverityNumber.WARN4,
    35: SeverityNumber.WARN4,
    36: SeverityNumber.WARN4,
    37: SeverityNumber.WARN4,
    38: SeverityNumber.WARN4,
    39: SeverityNumber.WARN4,
    40: SeverityNumber.ERROR,
    41: SeverityNumber.ERROR2,
    42: SeverityNumber.ERROR3,
    43: SeverityNumber.ERROR4,
    44: SeverityNumber.ERROR4,
    45: SeverityNumber.ERROR4,
    46: SeverityNumber.ERROR4,
    47: SeverityNumber.ERROR4,
    48: SeverityNumber.ERROR4,
    49: SeverityNumber.ERROR4,
    50: SeverityNumber.FATAL,
    51: SeverityNumber.FATAL2,
    52: SeverityNumber.FATAL3,
    53: SeverityNumber.FATAL4,
}


def std_to_otel(levelno: int) -> SeverityNumber:
    """
    Map python log levelno to OTel log severity number.
    Based on the SDK's LoggingHandler implementation.
    """
    if levelno < 10:
        return SeverityNumber.UNSPECIFIED
    if levelno > 53:
        return SeverityNumber.FATAL4
    return _STD_TO_OTEL[levelno]


class OpenTelemetryProcessor:
    """
    A structlog processor that translates structlog events into OpenTelemetry LogRecords.

    This processor should be added to the structlog processor chain to emit logs
    to OpenTelemetry. It translates structlog's event dictionary format into the
    OpenTelemetry Logs data model.

    Args:
        logger_provider: The LoggerProvider to use. If None, uses the global provider.
    """

    def __init__(self, logger_provider=None):
        """Initialize the processor with an optional logger provider."""
        self._logger_provider = logger_provider or get_logger_provider()

    def __call__(self, logger, name: str, event_dict: dict) -> dict:
        """
        Process a structlog event and emit it as an OpenTelemetry log.

        This method implements the structlog processor interface. It receives
        the event dictionary, translates it to an OTel LogRecord, and emits it.

        Args:
            logger: The structlog logger instance (unused).
            name: The logger name.
            event_dict: The structlog event dictionary.

        Returns:
            The unmodified event_dict (passthrough for other processors).
        """
        otel_logger = get_logger(name, logger_provider=self._logger_provider)

        # Skip emission if we have a no-op logger
        if not isinstance(otel_logger, NoOpLogger):
            log_record = self._translate(event_dict)
            otel_logger.emit(log_record)

        return event_dict

    def _get_attributes(self, event_dict: dict) -> dict[str, Any]:
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
            k: v for k, v in event_dict.items()
            if k not in _STRUCTLOG_RESERVED_KEYS
        }

        # Handle exception information
        exc_info = event_dict.get("exc_info")

        if exc_info is True:
            # exc_info=True means "get current exception"
            exc_info = sys.exc_info()

        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            exctype, value, tb = exc_info
            if exctype is not None:
                attributes[exception_attributes.EXCEPTION_TYPE] = exctype.__name__
            if value is not None and value.args:
                attributes[exception_attributes.EXCEPTION_MESSAGE] = str(value.args[0])
            if tb is not None:
                attributes[exception_attributes.EXCEPTION_STACKTRACE] = (
                    "".join(traceback.format_exception(*exc_info))
                )

        # Handle pre-rendered exception string (from structlog's ExceptionRenderer)
        exception_str = event_dict.get("exception")
        if isinstance(exception_str, str):
            # If we don't already have a stacktrace from exc_info, use this
            if exception_attributes.EXCEPTION_STACKTRACE not in attributes:
                attributes[exception_attributes.EXCEPTION_STACKTRACE] = exception_str

        return attributes

    def _translate(self, event_dict: dict) -> LogRecord:
        """
        Translate a structlog event dictionary into an OpenTelemetry LogRecord.

        Args:
            event_dict: The structlog event dictionary.

        Returns:
            An OpenTelemetry LogRecord.
        """
        # Use current time for both timestamp and observed_timestamp
        # structlog's timestamps are unreliable/varied depending on configuration
        timestamp = observed_timestamp = time_ns()

        # Get the log level and map to OTel severity
        level_str = event_dict.get("level", "info")
        levelno = _STRUCTLOG_LEVEL_TO_LEVELNO.get(level_str.lower(), 20)
        severity_number = std_to_otel(levelno)

        # Normalize severity text: "warning" -> "WARN", otherwise uppercase
        if level_str.lower() == "warning":
            severity_text = "WARN"
        else:
            severity_text = level_str.upper()

        # Get the message body
        body = event_dict.get("event")

        # Get attributes (filters reserved keys and extracts exception info)
        attributes = self._get_attributes(event_dict)

        # Get the current OTel context (includes trace context and baggage)
        context = get_current() or None

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

        This method flushes any pending logs. It runs in a separate thread
        to avoid potential deadlocks, following the pattern from the SDK's
        LoggingHandler.
        """
        if hasattr(self._logger_provider, "force_flush") and callable(
            self._logger_provider.force_flush
        ):
            thread = threading.Thread(target=self._logger_provider.force_flush)
            thread.start()


class StructlogInstrumentor(BaseInstrumentor):
    """
    An instrumentor for the structlog logging library.

    This instrumentor adds an OpenTelemetryProcessor to the structlog processor
    chain, enabling automatic emission of structlog events as OpenTelemetry logs.

    Example:
        >>> from opentelemetry.instrumentation.structlog import StructlogInstrumentor
        >>> import structlog
        >>> StructlogInstrumentor().instrument()
        >>> logger = structlog.get_logger()
        >>> logger.info("hello", user="alice")
    """

    _processor = None

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the required instrumentation dependencies."""
        return _instruments

    def _instrument(self, **kwargs):
        """
        Add the OpenTelemetryProcessor to structlog's processor chain.

        Args:
            logger_provider: Optional LoggerProvider to use.
        """
        # Create the OTel processor
        logger_provider = kwargs.get("logger_provider")
        processor = OpenTelemetryProcessor(logger_provider=logger_provider)

        # Get current structlog configuration
        config = structlog.get_config()
        current_processors = list(config.get("processors", []))

        # Insert the OTel processor before the last processor (typically the renderer)
        # This ensures we capture the event before it's formatted
        if current_processors:
            insert_position = len(current_processors) - 1
        else:
            insert_position = 0

        current_processors.insert(insert_position, processor)

        # Reconfigure structlog with the new processor chain
        structlog.configure(processors=current_processors)

        # Store reference for uninstrumentation
        StructlogInstrumentor._processor = processor

    def _uninstrument(self, **kwargs):
        """
        Remove the OpenTelemetryProcessor from structlog's processor chain.
        """
        if StructlogInstrumentor._processor is None:
            return

        # Get current structlog configuration
        config = structlog.get_config()
        current_processors = list(config.get("processors", []))

        # Remove all OpenTelemetryProcessor instances
        new_processors = [
            p for p in current_processors
            if not isinstance(p, OpenTelemetryProcessor)
        ]

        # Reconfigure structlog
        structlog.configure(processors=new_processors)

        # Clear reference
        StructlogInstrumentor._processor = None
