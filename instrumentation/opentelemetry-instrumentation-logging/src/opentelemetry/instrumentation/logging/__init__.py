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

"""
The OpenTelemetry `logging` integration automatically injects tracing context into
log statements, though it is opt-in and must be enabled explicitly by setting the
environment variable `OTEL_PYTHON_LOG_CORRELATION` to `true`.

.. code-block:: python

    import logging

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument()

    logging.warning('OTel test')

When running the above example you will see the following output:

::

    2025-03-05 09:40:04,398 WARNING [root] [example.py:7] [trace_id=0 span_id=0 resource.service.name= trace_sampled=False] - OTel test

The environment variable `OTEL_PYTHON_LOG_CORRELATION` must be set to `true`
in order to enable trace context injection into logs by calling
`logging.basicConfig()` and setting a logging format that makes use of the
injected tracing variables.

Alternatively, `set_logging_format` argument can be set to `True` when
initializing the `LoggingInstrumentor` class to achieve the same effect:

.. code-block:: python

    import logging

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument(set_logging_format=True)

    logging.warning('OTel test')

"""

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
    Span,
    TracerProvider,
    get_current_span,
    get_tracer_provider,
)

__doc__ = _MODULE_DOC  # noqa: A001

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
            set_logging_format is set to True.
        log_level: Accepts one of the following values and sets the logging level to it.
            logging.INFO
            logging.DEBUG
            logging.WARN
            logging.ERROR
            logging.FATAL
        log_hook: execute custom logic when record is created

    See `BaseInstrumentor`
    """

    _old_factory: Callable[..., logging.LogRecord] = None

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return python packages that the will be instrumented."""
        return _instruments

    # pylint: disable=R0914
    def _instrument(
        self,
        tracer_provider: Optional[TracerProvider] = None,
        log_hook: Optional[Callable[[Span, logging.LogRecord], None]] = None,
        set_logging_format: Optional[bool] = None,
        logging_format: Optional[str] = None,
        log_level: Optional[str] = None,
        trace_id_field: str = "otelTraceID",
        span_id_field: str = "otelSpanID",
        trace_sampled_field: str = "otelTraceSampled",
        service_name_field: str = "otelServiceName",
        **_kwargs,
    ) -> None:
        """Replace original log factory."""
        if tracer_provider is None:
            tracer_provider = get_tracer_provider()

        service_name = self._get_service_name(tracer_provider)
        old_factory = self._get_old_factory()

        def record_factory(*args, **kwargs) -> logging.LogRecord:
            """Create log record and fill tracing info to the fields."""
            record = old_factory(*args, **kwargs)

            setattr(record, service_name_field, service_name)
            setattr(record, trace_id_field, "0")
            setattr(record, trace_sampled_field, False)
            setattr(record, span_id_field, "0")

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
            """Create record and call log hook."""
            record = record_factory(*args, **kwargs)
            span = get_current_span()
            with suppress(Exception):
                log_hook(span, record)
            return record

        _factory = record_factory_with_hook if log_hook else record_factory
        logging.setLogRecordFactory(_factory)

        if self._logging_format_is_enabled(set_logging_format):
            self._set_logging_format(logging_format, log_level)

    def _uninstrument(self, **kwargs) -> None:
        """Turn back old log record factory."""
        self._set_old_factory()

    @staticmethod
    def _get_service_name(provider: TracerProvider) -> str:
        """Get service name from provider."""
        resource: Optional[Resource] = getattr(provider, "resource", None)
        if resource is None:
            return ""

        return resource.attributes.get("service.name", "")

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

    @staticmethod
    def _logging_format_is_enabled(
        set_logging_format: Optional[bool] = None,
    ) -> bool:
        """Check logging format is enabled."""
        if set_logging_format is None:
            env_value = environ.get(
                OTEL_PYTHON_LOG_CORRELATION, "false"
            ).lower()
            return env_value == "true"

        return set_logging_format

    @staticmethod
    def _set_logging_format(
        logging_format: Optional[str] = None,
        log_level: Optional[str] = None,
    ) -> None:
        """Set logging format."""
        if logging_format is None:
            logging_format = environ.get(OTEL_PYTHON_LOG_FORMAT, None)
        log_format = logging_format or DEFAULT_LOGGING_FORMAT

        if log_level is None:
            env_value = environ.get(OTEL_PYTHON_LOG_LEVEL, "")
            log_level = LEVELS.get(env_value.lower())
        log_level = log_level or logging.INFO

        logging.basicConfig(format=log_format, level=log_level)
