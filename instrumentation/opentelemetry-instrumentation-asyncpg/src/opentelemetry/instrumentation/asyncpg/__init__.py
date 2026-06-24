# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
This library allows tracing PostgreSQL queries made by the
`asyncpg <https://magicstack.github.io/asyncpg/current/>`_ library.

Usage
-----

Start PostgreSQL:

::

    docker run -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DATABASE=database -p 5432:5432 postgres

Run instrumented code:

.. code-block:: python

    import asyncio
    import asyncpg
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

    # You can optionally pass a custom TracerProvider to AsyncPGInstrumentor.instrument()
    AsyncPGInstrumentor().instrument()

    async def main():
        conn = await asyncpg.connect(user='user', password='password')

        await conn.fetch('''SELECT 42;''')

        await conn.close()

    asyncio.run(main())

API
---
"""

import re
from typing import Collection

import asyncpg
import asyncpg.prepared_stmt
import wrapt

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _set_db_name,
    _set_db_statement,
    _set_db_system,
    _set_db_user,
    _set_http_net_peer_name_client,
    _set_http_peer_port_client,
    _set_net_transport,
    _StabilityMode,
)
from opentelemetry.instrumentation.asyncpg.package import _instruments
from opentelemetry.instrumentation.asyncpg.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DbSystemValues,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NetTransportValues,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.network_attributes import (
    NetworkTransportValues,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode

_PREPARED_STMT_METHODS = (
    "fetch",
    "fetchval",
    "fetchrow",
    "executemany",
    "fetchmany",
)


def _hydrate_span_from_args(
    connection,
    query,
    parameters,
    sem_conv_opt_in_mode_db=_StabilityMode.DEFAULT,
    sem_conv_opt_in_mode_http=_StabilityMode.DEFAULT,
) -> dict:
    span_attributes: dict = {}
    _set_db_system(
        span_attributes,
        DbSystemValues.POSTGRESQL.value,
        sem_conv_opt_in_mode_db,
    )

    # connection contains _params attribute which is a namedtuple ConnectionParameters.
    # https://github.com/MagicStack/asyncpg/blob/master/asyncpg/connection.py#L68

    params = getattr(connection, "_params", None)
    dbname = getattr(params, "database", None)
    if dbname:
        _set_db_name(span_attributes, dbname, sem_conv_opt_in_mode_db)
    user = getattr(params, "user", None)
    if user:
        _set_db_user(span_attributes, user, sem_conv_opt_in_mode_db)

    # connection contains _addr attribute which is either a host/port tuple, or unix socket string
    # https://magicstack.github.io/asyncpg/current/_modules/asyncpg/connection.html
    addr = getattr(connection, "_addr", None)
    if isinstance(addr, tuple):
        _set_http_net_peer_name_client(
            span_attributes, addr[0], sem_conv_opt_in_mode_http
        )
        _set_http_peer_port_client(
            span_attributes, addr[1], sem_conv_opt_in_mode_http
        )
        _set_net_transport(
            span_attributes,
            NetTransportValues.IP_TCP.value,
            NetworkTransportValues.TCP.value,
            sem_conv_opt_in_mode_http,
        )
    elif isinstance(addr, str):
        _set_http_net_peer_name_client(
            span_attributes, addr, sem_conv_opt_in_mode_http
        )
        _set_net_transport(
            span_attributes,
            NetTransportValues.OTHER.value,
            NetworkTransportValues.PIPE.value,
            sem_conv_opt_in_mode_http,
        )

    if query is not None:
        _set_db_statement(span_attributes, query, sem_conv_opt_in_mode_db)

    if parameters is not None and len(parameters) > 0:
        span_attributes["db.statement.parameters"] = str(parameters)

    return span_attributes


class AsyncPGInstrumentor(BaseInstrumentor):
    _leading_comment_remover = re.compile(r"^/\*.*?\*/")
    _tracer = None

    def __init__(self, capture_parameters=False):
        super().__init__()
        self.capture_parameters = capture_parameters

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        _OpenTelemetrySemanticConventionStability._initialize()
        self._semconv_opt_in_mode_db = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE,
        )
        self._semconv_opt_in_mode_http = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP,
        )
        self._tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=_get_schema_url_for_signal_types(
                [
                    _OpenTelemetryStabilitySignalType.DATABASE,
                    _OpenTelemetryStabilitySignalType.HTTP,
                ]
            ),
        )

        for method in [
            "Connection.execute",
            "Connection.executemany",
            "Connection.fetch",
            "Connection.fetchval",
            "Connection.fetchrow",
        ]:
            wrapt.wrap_function_wrapper(
                "asyncpg.connection", method, self._do_execute
            )

        for method in [
            "Cursor.fetch",
            "Cursor.forward",
            "Cursor.fetchrow",
            "CursorIterator.__anext__",
        ]:
            wrapt.wrap_function_wrapper(
                "asyncpg.cursor", method, self._do_cursor_execute
            )

        for method in _PREPARED_STMT_METHODS:
            if hasattr(asyncpg.prepared_stmt.PreparedStatement, method):
                wrapt.wrap_function_wrapper(
                    "asyncpg.prepared_stmt",
                    f"PreparedStatement.{method}",
                    self._do_prepared_execute,
                )

    def _uninstrument(self, **__):
        for cls, methods in [
            (
                asyncpg.connection.Connection,
                ("execute", "executemany", "fetch", "fetchval", "fetchrow"),
            ),
            (asyncpg.cursor.Cursor, ("forward", "fetch", "fetchrow")),
            (asyncpg.cursor.CursorIterator, ("__anext__",)),
        ]:
            for method_name in methods:
                unwrap(cls, method_name)

        for method_name in _PREPARED_STMT_METHODS:
            if hasattr(asyncpg.prepared_stmt.PreparedStatement, method_name):
                unwrap(asyncpg.prepared_stmt.PreparedStatement, method_name)

    async def _do_execute(self, func, instance, args, kwargs):
        exception = None
        params = getattr(instance, "_params", None)
        name = (
            args[0] if args[0] else getattr(params, "database", "postgresql")
        )

        try:
            # Strip leading comments so we get the operation name.
            name = self._leading_comment_remover.sub("", name).split()[0]
        except IndexError:
            name = ""

        # Hydrate attributes before span creation to enable filtering
        span_attributes = _hydrate_span_from_args(
            instance,
            args[0],
            args[1:] if self.capture_parameters else None,
            sem_conv_opt_in_mode_db=self._semconv_opt_in_mode_db,
            sem_conv_opt_in_mode_http=self._semconv_opt_in_mode_http,
        )

        with self._tracer.start_as_current_span(
            name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                raise
            finally:
                if span.is_recording() and exception is not None:
                    span.set_status(Status(StatusCode.ERROR))
                    if _report_new(
                        self._semconv_opt_in_mode_db
                    ) or _report_new(self._semconv_opt_in_mode_http):
                        span.set_attribute(
                            ERROR_TYPE, type(exception).__qualname__
                        )

        return result

    async def _do_cursor_execute(self, func, instance, args, kwargs):
        """Wrap cursor based functions. For every call this will generate a new span."""
        exception = None
        params = getattr(instance._connection, "_params", None)
        name = (
            instance._query
            if instance._query
            else getattr(params, "database", "postgresql")
        )

        try:
            # Strip leading comments so we get the operation name.
            name = self._leading_comment_remover.sub("", name).split()[0]
        except IndexError:
            name = ""

        # Hydrate attributes before span creation to enable filtering
        span_attributes = _hydrate_span_from_args(
            instance._connection,
            instance._query,
            instance._args if self.capture_parameters else None,
            sem_conv_opt_in_mode_db=self._semconv_opt_in_mode_db,
            sem_conv_opt_in_mode_http=self._semconv_opt_in_mode_http,
        )

        stop = False
        with self._tracer.start_as_current_span(
            f"CURSOR: {name}",
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as span:
            try:
                result = await func(*args, **kwargs)
            except StopAsyncIteration:
                # Do not show this exception to the span
                stop = True
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                raise
            finally:
                if span.is_recording() and exception is not None:
                    span.set_status(Status(StatusCode.ERROR))
                    if _report_new(
                        self._semconv_opt_in_mode_db
                    ) or _report_new(self._semconv_opt_in_mode_http):
                        span.set_attribute(
                            ERROR_TYPE, type(exception).__qualname__
                        )

        if not stop:
            return result
        raise StopAsyncIteration

    async def _do_prepared_execute(self, func, instance, args, kwargs):
        exception = None
        query = instance._query or ""

        try:
            name = self._leading_comment_remover.sub("", query).split()[0]
        except IndexError:
            name = ""

        span_attributes = _hydrate_span_from_args(
            instance._connection,
            query,
            args if self.capture_parameters else None,
            sem_conv_opt_in_mode_db=self._semconv_opt_in_mode_db,
            sem_conv_opt_in_mode_http=self._semconv_opt_in_mode_http,
        )

        with self._tracer.start_as_current_span(
            name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                raise
            finally:
                if span.is_recording() and exception is not None:
                    span.set_status(Status(StatusCode.ERROR))
                    if _report_new(
                        self._semconv_opt_in_mode_db
                    ) or _report_new(self._semconv_opt_in_mode_http):
                        span.set_attribute(
                            ERROR_TYPE, type(exception).__qualname__
                        )

        return result
