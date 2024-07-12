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
import traceback
from time import time_ns

from opentelemetry._logs import (
    LogRecord,
    NoOpLogger,
    get_logger,
    get_logger_provider,
    std_to_otel,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from opentelemetry.util.types import Attributes

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

    def __init__(
        self,
        level=logging.NOTSET,
        logger_provider=None,
    ) -> None:
        super().__init__(level=level)
        self._logger_provider = logger_provider or get_logger_provider()
        self._logger = get_logger(
            __name__, logger_provider=self._logger_provider
        )

    @staticmethod
    def _get_attributes(record: logging.LogRecord) -> Attributes:
        attributes = {
            k: v for k, v in vars(record).items() if k not in _RESERVED_ATTRS
        }

        # Add standard code attributes for logs.
        attributes[SpanAttributes.CODE_FILEPATH] = record.pathname
        attributes[SpanAttributes.CODE_FUNCTION] = record.funcName
        attributes[SpanAttributes.CODE_LINENO] = record.lineno

        if record.exc_info:
            exctype, value, tb = record.exc_info
            if exctype is not None:
                attributes[SpanAttributes.EXCEPTION_TYPE] = exctype.__name__
            if value is not None and value.args:
                attributes[SpanAttributes.EXCEPTION_MESSAGE] = value.args[0]
            if tb is not None:
                # https://github.com/open-telemetry/opentelemetry-specification/blob/9fa7c656b26647b27e485a6af7e38dc716eba98a/specification/trace/semantic_conventions/exceptions.md#stacktrace-representation
                attributes[SpanAttributes.EXCEPTION_STACKTRACE] = "".join(
                    traceback.format_exception(*record.exc_info)
                )
        return attributes

    def _translate(self, record: logging.LogRecord) -> LogRecord:
        timestamp = int(record.created * 1e9)
        observered_timestamp = time_ns()
        span_context = get_current_span().get_span_context()
        attributes = self._get_attributes(record)
        # This comment is taken from GanyedeNil's PR #3343, I have redacted it
        # slightly for clarity:
        # According to the definition of the Body field type in the
        # OTel 1.22.0 Logs Data Model article, the Body field should be of
        # type 'any' and should not use the str method to directly translate
        # the msg. This is because str only converts non-text types into a
        # human-readable form, rather than a standard format, which leads to
        # the need for additional operations when collected through a log
        # collector.
        # Considering that he Body field should be of type 'any' and should not
        # use the str method but record.msg is also a string type, then the
        # difference is just the self.args formatting?
        # The primary consideration depends on the ultimate purpose of the log.
        # Converting the default log directly into a string is acceptable as it
        # will be required to be presented in a more readable format. However,
        # this approach might not be as "standard" when hoping to aggregate
        # logs and perform subsequent data analysis. In the context of log
        # extraction, it would be more appropriate for the msg to be
        # converted into JSON format or remain unchanged, as it will eventually
        # be transformed into JSON. If the final output JSON data contains a
        # structure that appears similar to JSON but is not, it may confuse
        # users. This is particularly true for operation and maintenance
        # personnel who need to deal with log data in various languages.
        # Where is the JSON converting occur? and what about when the msg
        # represents something else but JSON, the expected behavior change?
        # For the ConsoleLogExporter, it performs the to_json operation in
        # opentelemetry.sdk._logs._internal.export.ConsoleLogExporter.__init__,
        # so it can handle any type of input without problems. As for the
        # OTLPLogExporter, it also handles any type of input encoding in
        # _encode_log located in
        # opentelemetry.exporter.otlp.proto.common._internal._log_encoder.
        # Therefore, no extra operation is needed to support this change.
        # The only thing to consider is the users who have already been using
        # this SDK. If they upgrade the SDK after this change, they will need
        # to readjust their logging collection rules to adapt to the latest
        # output format. Therefore, this change is considered a breaking
        # change and needs to be upgraded at an appropriate time.
        severity_number = std_to_otel(record.levelno)
        if isinstance(record.msg, str) and record.args:
            body = record.msg % record.args
        else:
            body = record.msg

        # related to https://github.com/open-telemetry/opentelemetry-python/issues/3548
        # Severity Text = WARN as defined in https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/logs/data-model.md#displaying-severity.
        level_name = (
            "WARN" if record.levelname == "WARNING" else record.levelname
        )

        return LogRecord(
            timestamp=timestamp,
            observed_timestamp=observered_timestamp,
            trace_id=span_context.trace_id,
            span_id=span_context.span_id,
            trace_flags=span_context.trace_flags,
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
        if not isinstance(self._logger, NoOpLogger):
            self._logger.emit(self._translate(record))
