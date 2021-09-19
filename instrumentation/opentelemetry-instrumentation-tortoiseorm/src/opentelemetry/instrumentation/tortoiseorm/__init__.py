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
Instrument `tortoise-orm`_ to report SQL queries.
Usage
-----
.. code:: python
    from opentelemetry.instrumentation.tortoiseorm import TortoiseORMInstrumentor
    from tortoise.contrib.fastapi import register_tortoise

    register_tortoise(
        app,
        db_url=settings.db_url,
        modules={"models": ["example_app.db_models"]},
        generate_schemas=True,
        add_exception_handlers=True,
    )

    TortoiseORMInstrumentor().instrument(tracer_provider=tracer)
API
---
"""
from typing import Collection

try:
    import tortoise.backends.asyncpg.client

    TORTOISE_POSTGRES_SUPPORT = True
except ModuleNotFoundError:
    TORTOISE_POSTGRES_SUPPORT = False

try:
    import tortoise.backends.mysql.client

    TORTOISE_MYSQL_SUPPORT = True
except ModuleNotFoundError:
    TORTOISE_MYSQL_SUPPORT = False

try:
    import tortoise.backends.sqlite.client

    TORTOISE_SQLITE_SUPPORT = True
except ModuleNotFoundError:
    TORTOISE_SQLITE_SUPPORT = False

import wrapt

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.tortoiseorm.package import _instruments
from opentelemetry.instrumentation.tortoiseorm.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import DbSystemValues, SpanAttributes
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode


def _hydrate_span_from_args(connection, query, parameters) -> dict:
    """Get network and database attributes from connection."""
    span_attributes = {}
    capabilities = getattr(connection, "capabilities", None)
    if capabilities:
        if capabilities.dialect == "sqlite":
            span_attributes[SpanAttributes.DB_SYSTEM] = DbSystemValues.SQLITE.value
        elif capabilities.dialect == "postgres":
            span_attributes[SpanAttributes.DB_SYSTEM] = DbSystemValues.POSTGRESQL.value
        elif capabilities.dialect == "mysql":
            span_attributes[SpanAttributes.DB_SYSTEM] = DbSystemValues.MYSQL.value
    dbname = getattr(connection, "filename", None)
    if dbname:
        span_attributes[SpanAttributes.DB_NAME] = dbname
    dbname = getattr(connection, "database", None)
    if dbname:
        span_attributes[SpanAttributes.DB_NAME] = dbname
    if query is not None:
        span_attributes[SpanAttributes.DB_STATEMENT] = query
    user = getattr(connection, "user", None)
    if user:
        span_attributes[SpanAttributes.DB_USER] = user
    host = getattr(connection, "host", None)
    if host:
        span_attributes[SpanAttributes.NET_PEER_NAME] = host
    port = getattr(connection, "port", None)
    if port:
        span_attributes[SpanAttributes.NET_PEER_PORT] = port

    if parameters is not None and len(parameters) > 0:
        span_attributes["db.statement.parameters"] = str(parameters)

    return span_attributes


class TortoiseORMInstrumentor(BaseInstrumentor):
    """An instrumentor for Tortoise-ORM
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments Tortoise ORM backend methods.
        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
        Returns:
            None
        """
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = trace.get_tracer(__name__, __version__, tracer_provider)
        if TORTOISE_SQLITE_SUPPORT:
            funcs = [
                "SqliteClient.execute_many",
                "SqliteClient.execute_query",
                "SqliteClient.execute_insert",
                "SqliteClient.execute_query_dict",
                "SqliteClient.execute_script",
            ]
            for f in funcs:
                wrapt.wrap_function_wrapper(
                    "tortoise.backends.sqlite.client",
                    f,
                    self._do_execute,
                )

        if TORTOISE_POSTGRES_SUPPORT:
            funcs = [
                "AsyncpgDBClient.execute_many",
                "AsyncpgDBClient.execute_query",
                "AsyncpgDBClient.execute_insert",
                "AsyncpgDBClient.execute_query_dict",
                "AsyncpgDBClient.execute_script",
            ]
            for f in funcs:
                wrapt.wrap_function_wrapper(
                    "tortoise.backends.asyncpg.client",
                    f,
                    self._do_execute,
                )

        if TORTOISE_MYSQL_SUPPORT:
            funcs = [
                "MySQLClient.execute_many",
                "MySQLClient.execute_query",
                "MySQLClient.execute_insert",
                "MySQLClient.execute_query_dict",
                "MySQLClient.execute_script",
            ]
            for f in funcs:
                wrapt.wrap_function_wrapper(
                    "tortoise.backends.mysql.client",
                    f,
                    self._do_execute,
                )

    def _uninstrument(self, **kwargs):
        if TORTOISE_SQLITE_SUPPORT:
            unwrap(tortoise.backends.sqlite.client.SqliteClient, "execute_query")
            unwrap(tortoise.backends.sqlite.client.SqliteClient, "execute_many")
            unwrap(tortoise.backends.sqlite.client.SqliteClient, "execute_insert")
            unwrap(tortoise.backends.sqlite.client.SqliteClient, "execute_query_dict")
            unwrap(tortoise.backends.sqlite.client.SqliteClient, "execute_script")
        if TORTOISE_MYSQL_SUPPORT:
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_query")
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_many")
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_insert")
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_query_dict")
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_script")
        if self.TORTOISE_POSTGRES_SUPPORT:
            unwrap(tortoise.backends.asyncpg.client.AsyncpgDBClient, "execute_query")
            unwrap(tortoise.backends.asyncpg.client.AsyncpgDBClient, "execute_many")
            unwrap(tortoise.backends.asyncpg.client.AsyncpgDBClient, "execute_insert")
            unwrap(
                tortoise.backends.asyncpg.client.AsyncpgDBClient, "execute_query_dict"
            )
            unwrap(tortoise.backends.asyncpg.client.AsyncpgDBClient, "execute_script")

    async def _do_execute(self, func, instance, args, kwargs):

        exception = None
        name = args[0]

        with self._tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
            if span.is_recording():
                span_attributes = _hydrate_span_from_args(
                    instance,
                    args[0],
                    args[1:],
                )
                for attribute, value in span_attributes.items():
                    span.set_attribute(attribute, value)

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                raise
            finally:
                if span.is_recording() and exception is not None:
                    span.set_status(Status(StatusCode.ERROR))

        return result
