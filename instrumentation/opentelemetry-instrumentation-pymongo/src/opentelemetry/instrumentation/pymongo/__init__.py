# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
The integration with MongoDB supports the `pymongo`_ library, it can be
enabled using the ``PymongoInstrumentor``.

.. _pymongo: https://pypi.org/project/pymongo

Usage
-----

.. code:: python

    from pymongo import MongoClient
    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

    PymongoInstrumentor().instrument()
    client = MongoClient()
    db = client["MongoDB_Database"]
    collection = db["MongoDB_Collection"]
    collection.find_one()

API
---
The `instrument` method accepts the following keyword args:

* tracer_provider (``TracerProvider``) - an optional tracer provider
* request_hook (``Callable[[Span, CommandStartedEvent], None]``) - a function with extra user-defined logic to be performed before querying mongodb
* response_hook (``Callable[[Span, CommandSucceededEvent], None]``) - a function with extra user-defined logic to be performed after the query returns with a successful response
* failed_hook (``Callable[[Span, CommandFailedEvent], None]``) - a function with extra user-defined logic to be performed after the query returns with a failed response
* capture_statement (``bool``) - an optional value to enable capturing the database statement that is being executed

for example:

.. code:: python

    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
    from pymongo import MongoClient

    def request_hook(span, event):
        # request hook logic
        pass

    def response_hook(span, event):
        # response hook logic
        pass

    def failed_hook(span, event):
        # failed hook logic
        pass

    # Instrument pymongo with hooks
    PymongoInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook, failed_hook=failed_hook)

    # This will create a span with pymongo specific attributes, including custom attributes added from the hooks
    client = MongoClient()
    db = client["MongoDB_Database"]
    collection = db["MongoDB_Collection"]
    collection.find_one()

"""

from __future__ import annotations

from logging import getLogger
from typing import Any, Callable, Collection, TypeVar

from pymongo import monitoring

from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _report_old,
    _set_db_name,
    _set_db_statement,
    _set_db_system,
    _set_http_net_peer_name_client,
    _set_http_peer_port_client,
    _StabilityMode,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.pymongo.package import _instruments
from opentelemetry.instrumentation.pymongo.utils import (
    COMMAND_TO_ATTRIBUTE_MAPPING,
)
from opentelemetry.instrumentation.pymongo.version import __version__
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_MONGODB_COLLECTION,
    DbSystemValues,
)
from opentelemetry.semconv.attributes.db_attributes import DB_COLLECTION_NAME
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, Tracer, get_tracer
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import Status, StatusCode

_LOG = getLogger(__name__)

RequestHookT = Callable[[Span, monitoring.CommandStartedEvent], None]
ResponseHookT = Callable[[Span, monitoring.CommandSucceededEvent], None]
FailedHookT = Callable[[Span, monitoring.CommandFailedEvent], None]

CommandEvent = TypeVar(
    "CommandEvent",
    monitoring.CommandStartedEvent,
    monitoring.CommandSucceededEvent,
    monitoring.CommandFailedEvent,
)


def dummy_callback(span: Span, event: CommandEvent): ...


class CommandTracer(monitoring.CommandListener):
    def __init__(
        self,
        tracer: Tracer,
        request_hook: RequestHookT = dummy_callback,
        response_hook: ResponseHookT = dummy_callback,
        failed_hook: FailedHookT = dummy_callback,
        capture_statement: bool = False,
        semconv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    ):
        self._tracer = tracer
        self._span_dict = {}
        self.is_enabled = True
        self.start_hook = request_hook
        self.success_hook = response_hook
        self.failed_hook = failed_hook
        self.capture_statement = capture_statement
        self._semconv_opt_in_mode = semconv_opt_in_mode

    def started(self, event: monitoring.CommandStartedEvent):
        """Method to handle a pymongo CommandStartedEvent"""
        if not self.is_enabled or not is_instrumentation_enabled():
            return
        command_name = event.command_name
        span_name = f"{event.database_name}.{command_name}"
        statement = self._get_statement_by_command_name(command_name, event)
        collection = _get_command_collection_name(event)

        try:
            span = self._tracer.start_span(span_name, kind=SpanKind.CLIENT)
            if span.is_recording():
                span_attributes: dict = {}
                _set_db_system(
                    span_attributes,
                    DbSystemValues.MONGODB.value,
                    self._semconv_opt_in_mode,
                )
                _set_db_name(
                    span_attributes,
                    event.database_name,
                    self._semconv_opt_in_mode,
                )
                _set_db_statement(
                    span_attributes,
                    statement,
                    self._semconv_opt_in_mode,
                )
                if collection:
                    if _report_old(self._semconv_opt_in_mode):
                        span_attributes[DB_MONGODB_COLLECTION] = collection
                    if _report_new(self._semconv_opt_in_mode):
                        span_attributes[DB_COLLECTION_NAME] = collection
                if event.connection_id is not None:
                    _set_http_net_peer_name_client(
                        span_attributes,
                        event.connection_id[0],
                        self._semconv_opt_in_mode,
                    )
                    _set_http_peer_port_client(
                        span_attributes,
                        event.connection_id[1],
                        self._semconv_opt_in_mode,
                    )
                span.set_attributes(span_attributes)
            try:
                self.start_hook(span, event)
            except (
                Exception  # noqa pylint: disable=broad-except
            ) as hook_exception:  # noqa pylint: disable=broad-except
                _LOG.exception(hook_exception)

            # Add Span to dictionary
            self._span_dict[_get_span_dict_key(event)] = span
        except Exception as ex:  # noqa pylint: disable=broad-except
            if span is not None and span.is_recording():
                span.set_status(Status(StatusCode.ERROR, str(ex)))
                if _report_new(self._semconv_opt_in_mode):
                    span.set_attribute(ERROR_TYPE, type(ex).__qualname__)
                span.end()
                self._pop_span(event)

    def succeeded(self, event: monitoring.CommandSucceededEvent):
        """Method to handle a pymongo CommandSucceededEvent"""
        if not self.is_enabled or not is_instrumentation_enabled():
            return
        span = self._pop_span(event)
        if span is None:
            return
        if span.is_recording():
            try:
                self.success_hook(span, event)
            except (
                Exception  # noqa pylint: disable=broad-except
            ) as hook_exception:  # noqa pylint: disable=broad-except
                _LOG.exception(hook_exception)
        span.end()

    def failed(self, event: monitoring.CommandFailedEvent):
        """Method to handle a pymongo CommandFailedEvent"""
        if not (self.is_enabled and is_instrumentation_enabled()):
            return
        span = self._pop_span(event)
        if span is None:
            return
        if span.is_recording():
            span.set_status(
                Status(
                    StatusCode.ERROR,
                    event.failure.get("errmsg", "Unknown error"),
                )
            )
            if _report_new(self._semconv_opt_in_mode):
                span.set_attribute(
                    ERROR_TYPE, event.failure.get("codeName", "UnknownError")
                )
            try:
                self.failed_hook(span, event)
            except (
                Exception  # noqa pylint: disable=broad-except
            ) as hook_exception:  # noqa pylint: disable=broad-except
                _LOG.exception(hook_exception)
        span.end()

    def _pop_span(self, event: CommandEvent) -> Span | None:
        return self._span_dict.pop(_get_span_dict_key(event), None)

    def _get_statement_by_command_name(
        self, command_name: str, event: CommandEvent
    ) -> str:
        statement = command_name
        command_attribute = COMMAND_TO_ATTRIBUTE_MAPPING.get(command_name)
        command = event.command.get(command_attribute)
        if command and self.capture_statement:
            statement += " " + str(command)
        return statement


def _get_command_collection_name(event: CommandEvent) -> str | None:
    collection_name = event.command.get(event.command_name)
    if not collection_name or not isinstance(collection_name, str):
        return None
    return collection_name


def _get_span_dict_key(
    event: CommandEvent,
) -> int | tuple[int, tuple[str, int | None]]:
    if event.connection_id is not None:
        return event.request_id, event.connection_id
    return event.request_id


class PymongoInstrumentor(BaseInstrumentor):
    _commandtracer_instance: CommandTracer | None = None
    # The instrumentation for PyMongo is based on the event listener interface
    # https://api.mongodb.com/python/current/api/pymongo/monitoring.html.
    # This interface only allows to register listeners and does not provide
    # an unregister API. In order to provide a mechanishm to disable
    # instrumentation an enabled flag is implemented in CommandTracer,
    # it's checked in the different listeners.

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """Integrate with pymongo to trace it using event listener.
        https://api.mongodb.com/python/current/api/pymongo/monitoring.html

        Args:
            tracer_provider: The `TracerProvider` to use. If none is passed the
                current configured one is used.
        """

        tracer_provider = kwargs.get("tracer_provider")
        request_hook = kwargs.get("request_hook", dummy_callback)
        response_hook = kwargs.get("response_hook", dummy_callback)
        failed_hook = kwargs.get("failed_hook", dummy_callback)
        capture_statement = kwargs.get("capture_statement")
        # Create and register a CommandTracer only the first time
        if self._commandtracer_instance is None:
            _OpenTelemetrySemanticConventionStability._initialize()
            semconv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE,
            )
            tracer = get_tracer(
                __name__,
                __version__,
                tracer_provider,
                schema_url=_get_schema_url_for_signal_types(
                    [_OpenTelemetryStabilitySignalType.DATABASE]
                ),
            )

            self._commandtracer_instance = CommandTracer(
                tracer,
                request_hook=request_hook,
                response_hook=response_hook,
                failed_hook=failed_hook,
                capture_statement=capture_statement,
                semconv_opt_in_mode=semconv_opt_in_mode,
            )
            monitoring.register(self._commandtracer_instance)
        # If already created, just enable it
        self._commandtracer_instance.is_enabled = True

    def _uninstrument(self, **kwargs: Any):
        if self._commandtracer_instance is not None:
            self._commandtracer_instance.is_enabled = False
