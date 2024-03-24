"""OpenTelemetry processor for structlog."""

import traceback
from datetime import datetime, timezone
from typing import Dict

import structlog
from opentelemetry._logs import std_to_otel
from opentelemetry.sdk._logs._internal import LoggerProvider, LogRecord
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor, LogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from structlog._frames import _format_exception
from structlog._log_levels import NAME_TO_LEVEL
from structlog.processors import _figure_out_exc_info

_EXCLUDE_ATTRS = {"exception", "timestamp"}


class OpenTelemetryExporter:
    """A structlog processor that writes logs in OTLP format to a collector.

    Note: this will replace (or insert if not present) the `timestamp` key in the
    `event_dict` to be in an ISO 8601 format that is more widely recognized. This
    means that `structlog.processors.TimeStamper` is not required to be added to the
    processors list if this processor is used.

    Note: this also performs the operations done by
    `structlog.processors.ExceptionRenderer`. DO NOT use `ExceptionRenderer` in the
    same processor pipeline as this processor.
    """

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

    def _pre_process(
        self, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        event_dict["timestamp"] = datetime.now(timezone.utc)

        self._pre_process_exc_info(event_dict)

        return event_dict

    def _post_process(
        self, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        event_dict["timestamp"] = event_dict["timestamp"].isoformat()

        self._post_process_exc_info(event_dict)

        return event_dict

    def _pre_process_exc_info(
        self, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        exc_info = event_dict.pop("exc_info", None)
        if exc_info is not None:
            event_dict["exception"] = _figure_out_exc_info(exc_info)

        return event_dict

    def _post_process_exc_info(
        self, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        exception = event_dict.pop("exception", None)
        if exception is not None:
            event_dict["exception"] = _format_exception(exception)

        return event_dict

    def _translate(
        self,
        timestamp: int,
        extra_attrs: Dict[str, str],
        event_dict: structlog.typing.EventDict,
    ) -> LogRecord:
        span_context = get_current_span().get_span_context()
        # attributes = self._get_attributes(record)
        severity_number = std_to_otel(NAME_TO_LEVEL[event_dict["level"]])

        return LogRecord(
            timestamp=timestamp,
            trace_id=span_context.trace_id,
            span_id=span_context.span_id,
            trace_flags=span_context.trace_flags,
            severity_text=event_dict["level"],
            severity_number=severity_number,
            body=event_dict["event"],
            resource=self._logger.resource,
            attributes={
                **{k: v for k, v in event_dict.items() if k not in _EXCLUDE_ATTRS},
                **extra_attrs,
            },
        )

    @staticmethod
    def _parse_timestamp(event_dict: structlog.typing.EventDict) -> int:
        return int(event_dict["timestamp"].timestamp() * 1e9)

    @staticmethod
    def _parse_exception(event_dict: structlog.typing.EventDict) -> Dict[str, str]:
        # taken from: https://github.com/open-telemetry/opentelemetry-python/blob/c4d17e9f14f3cafb6757b96eefabdc7ed4891306/opentelemetry-sdk/src/opentelemetry/sdk/_logs/_internal/__init__.py#L458-L475
        attributes: Dict[str, str] = {}
        exception = event_dict.get("exception", None)
        if exception is not None:
            exc_type = ""
            message = ""
            stack_trace = ""
            exctype, value, tb = exception
            if exctype is not None:
                exc_type = exctype.__name__
            if value is not None and value.args:
                message = value.args[0]
            if tb is not None:
                # https://github.com/open-telemetry/opentelemetry-specification/blob/9fa7c656b26647b27e485a6af7e38dc716eba98a/specification/trace/semantic_conventions/exceptions.md#stacktrace-representation
                stack_trace = "".join(traceback.format_exception(*exception))
            attributes[SpanAttributes.EXCEPTION_TYPE] = exc_type
            attributes[SpanAttributes.EXCEPTION_MESSAGE] = message
            attributes[SpanAttributes.EXCEPTION_STACKTRACE] = stack_trace

        return attributes

    def __call__(
        self,
        logger: structlog.typing.WrappedLogger,
        name: str,
        event_dict: structlog.typing.EventDict,
    ):
        """Emit a record."""
        event_dict = self._pre_process(event_dict)
        timestamp = self._parse_timestamp(event_dict)
        extra_attrs = self._parse_exception(event_dict)
        event_dict = self._post_process(event_dict)

        self._logger.emit(self._translate(timestamp, extra_attrs, event_dict))

        return event_dict
