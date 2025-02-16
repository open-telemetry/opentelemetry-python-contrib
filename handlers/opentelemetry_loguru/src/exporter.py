import traceback
from datetime import datetime, timezone
from typing import Dict

import loguru
import traceback
from os import environ
from time import time_ns
from typing import Any, Callable, Optional, Tuple, Union  # noqa
from opentelemetry._logs import (
    NoOpLogger,
    SeverityNumber,
    get_logger,
    get_logger_provider,
    std_to_otel,
)
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.environment_variables import (
    OTEL_ATTRIBUTE_COUNT_LIMIT,
    OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.util import ns_to_iso_str
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import (
    format_span_id,
    format_trace_id,
    get_current_span,
)
from opentelemetry.trace.span import TraceFlags
from opentelemetry.util.types import Attributes

from opentelemetry._logs import Logger as APILogger
from opentelemetry._logs import LoggerProvider as APILoggerProvider
from opentelemetry._logs import LogRecord as APILogRecord

from opentelemetry._logs import std_to_otel
from opentelemetry.sdk._logs._internal import LoggerProvider, LogRecord
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor, LogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from opentelemetry._logs.severity import SeverityNumber

import sys
import json

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

EXCLUDE_ATTR = ("elapsed", "exception", "extra", "file", "level", "process", "thread", "time")
class LoguruHandler:

    # this was largely inspired by the OpenTelemetry handler for stdlib `logging`:
    # https://github.com/open-telemetry/opentelemetry-python/blob/8f312c49a5c140c14d1829c66abfe4e859ad8fd7/opentelemetry-sdk/src/opentelemetry/sdk/_logs/_internal/__init__.py#L318

    def __init__(
        self,
        service_name: str,
        server_hostname: str,
        exporter: LogExporter,
    ) -> None:
        logger_provider = LoggerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.instance.id": server_hostname,
                }
            ),
        )

        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter, max_export_batch_size=1)
        )

        self._logger_provider = logger_provider
        self._logger = logger_provider.get_logger(__name__)
        
        
    def _get_attributes(self, record) -> Attributes:
        attributes = {key:value for key, value in record.items() if key not in EXCLUDE_ATTR}
        
         # Add standard code attributes for logs.
        attributes[SpanAttributes.CODE_FILEPATH] = record['file'].path #This includes file and path -> (file, path)
        attributes[SpanAttributes.CODE_FUNCTION] = record['function']
        attributes[SpanAttributes.CODE_LINENO] = record['line']

        attributes['process_name'] = (record['process']).name
        attributes['process_id'] = (record['process']).id
        attributes['thread_name'] = (record['thread']).name
        attributes['thread_id'] = (record['thread']).id
        attributes['file'] = record['file'].name
        
        if record['exception'] is not None:

            attributes[SpanAttributes.EXCEPTION_TYPE] = record['exception'].type

            attributes[SpanAttributes.EXCEPTION_MESSAGE] = record['exception'].value

            attributes[SpanAttributes.EXCEPTION_STACKTRACE] = record['exception'].traceback
        
        return attributes

    def _loguru_to_otel(self, levelno: int) -> SeverityNumber:
        if levelno < 10 or levelno == 25:
            return SeverityNumber.UNSPECIFIED
        
        elif levelno > 53:
            return SeverityNumber.FATAL4
        
        return _STD_TO_OTEL[levelno]
    
  
        
        
    def _translate(self, record) -> LogRecord:
        
        #Timestamp
        timestamp = int((record["time"].timestamp()) * 1e9)
        
        #Observed timestamp
        observedTimestamp = time_ns()
        
        #Span context
        spanContext = get_current_span().get_span_context()
        
        #Setting the level name
        if  record['level'].name == 'WARNING':
            levelName = 'WARN'
        elif record['level'].name == 'TRACE' or record['level'].name == 'SUCCESS':
            levelName = 'NOTSET'
        else:
            levelName = record['level'].name

        #Severity number
        severityNumber = self._loguru_to_otel(int(record["level"].no)) 
        
        #Getting attributes
        attributes = self._get_attributes(record)
        
        
        return LogRecord(
            timestamp = timestamp,
            observed_timestamp = observedTimestamp,
            trace_id = spanContext.trace_id,
            span_id = spanContext.span_id,
            trace_flags = spanContext.trace_flags,
            severity_text = levelName,
            severity_number = severityNumber,
            body=record['message'],
            resource = self._logger.resource,
            attributes=attributes
        )

    def sink(self, record) -> None:
        self._logger.emit(self._translate(record.record))
    