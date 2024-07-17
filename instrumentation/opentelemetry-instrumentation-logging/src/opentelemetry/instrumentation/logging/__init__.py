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
from contextlib import suppress
from os import environ
from typing import Callable, Collection, Optional

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.logging.constants import (
    _MODULE_DOC,
    DEFAULT_LOGGING_FORMAT,
)
from opentelemetry.instrumentation.logging.environment_variables import (
    OTEL_PYTHON_LOG_CORRELATION,
    OTEL_PYTHON_LOG_FORMAT,
    OTEL_PYTHON_LOG_LEVEL,
)
from opentelemetry.instrumentation.logging.package import _instruments
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import (
    INVALID_SPAN,
    INVALID_SPAN_CONTEXT,
    TracerProvider,
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

    This instrumentor injects tracing context into logging records and optionally
    sets the global logging format to the following:

    .. code-block::

        {DEFAULT_LOGGING_FORMAT}

        def log_hook(span: Span, record: LogRecord):
                if span and span.is_recording():
                    record.custom_user_attribute_from_log_hook = "some-value"

    Args:
        tracer_provider: Tracer provider instance that can be used to fetch a tracer.
        set_logging_format: When set to True, it calls logging.basicConfig() and sets
        a logging format.
        logging_format: Accepts a string and sets it as the logging format when
        set_logging_format
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

    SPAN_ID_FIELD = "otelSpanID"
    TRACE_ID_FIELD = "otelTraceID"
    TRACE_SAMPLED_FIELD = "otelTraceSampled"
    SERVICE_NAME_FIELD = "otelServiceName"

    _old_factory: Callable[..., logging.LogRecord] = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _get_service_name(self, provider: TracerProvider) -> str:
        """Get service name from provider."""
        resource: Optional[Resource] = getattr(provider, "resource", None)
        if resource is None:
            return ""

        return resource.attributes.get("service.name", "")

    def _instrument(self, **_kwargs):
        provider = _kwargs.get("tracer_provider", get_tracer_provider())
        service_name = self._get_service_name(provider)
        old_factory = self._get_old_factory()
        log_hook: Optional[Callable] = _kwargs.get("log_hook", None)

        service_name_field = self.SERVICE_NAME_FIELD
        trace_id_field = self.TRACE_ID_FIELD
        trace_sampled_field = self.TRACE_SAMPLED_FIELD
        span_id_field = self.SPAN_ID_FIELD

        def record_factory(*args, **kwargs) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)

            setattr(record, service_name_field, service_name)
            setattr(record, trace_id_field, "0")
            setattr(record, trace_sampled_field, "0")
            setattr(record, span_id_field, False)

            span = get_current_span()
            if span == INVALID_SPAN:
                return record

            ctx = span.get_span_context()
            if ctx == INVALID_SPAN_CONTEXT:
                return record

            setattr(record, trace_id_field, format(ctx.trace_id, "032x"))
            setattr(record, trace_sampled_field, ctx.trace_flags.sampled)
            setattr(record, span_id_field, format(ctx.span_id, "016x"))

            return record

        def record_factory_with_hook(*args, **kwargs) -> logging.LogRecord:
            record = record_factory(*args, **kwargs)
            span = get_current_span()
            with suppress(Exception):
                log_hook(span, record)
            return record

        _factory = record_factory_with_hook if log_hook else record_factory
        logging.setLogRecordFactory(_factory)
        self._set_logging_format(**_kwargs)

    def _uninstrument(self, **kwargs):
        self._set_old_factory()

    def _get_old_factory(self) -> Callable[..., logging.LogRecord]:
        """Get and store original log factory."""
        old_factory = logging.getLogRecordFactory()
        self.__class__._old_factory = old_factory
        return old_factory

    def _set_old_factory(self) -> None:
        """Set original log factory."""
        old_factory = self.__class__._old_factory
        if old_factory is None:
            return

        logging.setLogRecordFactory(old_factory)
        self.__class__._old_factory = None

    def _set_logging_format(self, **kwargs):
        set_logging_format = kwargs.get(
            "set_logging_format",
            environ.get(OTEL_PYTHON_LOG_CORRELATION, "false").lower()
            == "true",
        )
        if not set_logging_format:
            return

        log_format = kwargs.get(
            "logging_format", environ.get(OTEL_PYTHON_LOG_FORMAT, None)
        )
        log_format = log_format or DEFAULT_LOGGING_FORMAT

        log_level = kwargs.get(
            "log_level", LEVELS.get(environ.get(OTEL_PYTHON_LOG_LEVEL))
        )
        log_level = log_level or logging.INFO

        logging.basicConfig(format=log_format, level=log_level)
