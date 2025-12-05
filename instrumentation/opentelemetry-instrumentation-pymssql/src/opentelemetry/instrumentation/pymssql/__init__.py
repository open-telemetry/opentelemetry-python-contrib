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
The integration with pymssql supports the `pymssql`_ library and can be enabled
by using ``PyMSSQLInstrumentor``.

.. _pymssql: https://pypi.org/project/pymssql/

Usage
-----

.. code:: python

    import pymssql
    from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor

    PyMSSQLInstrumentor().instrument()

    cnx = pymssql.connect(database="MSSQL_Database")
    cursor = cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cnx.commit()
    cursor.close()
    cnx.close()

.. code:: python

    import pymssql
    from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor

    # Alternatively, use instrument_connection for an individual connection
    cnx = pymssql.connect(database="MSSQL_Database")
    instrumented_cnx = PyMSSQLInstrumentor().instrument_connection(cnx)
    cursor = instrumented_cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    instrumented_cnx.commit()
    cursor.close()
    instrumented_cnx.close()

API
---
The `instrument` method accepts the following keyword args:

* tracer_provider (``TracerProvider``) - an optional tracer provider

For example:

.. code:: python

    import pymssql
    from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor
    from opentelemetry.trace import NoOpTracerProvider

    PyMSSQLInstrumentor().instrument(tracer_provider=NoOpTracerProvider())
"""

from __future__ import annotations

from typing import Any, Callable, Collection, NamedTuple

import pymssql

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.pymssql.package import _instruments
from opentelemetry.instrumentation.pymssql.version import __version__

_DATABASE_SYSTEM = "mssql"


class _PyMSSQLConnectMethodArgsTuple(NamedTuple):
    server: str | None = None
    user: str | None = None
    password: str | None = None
    database: str | None = None
    timeout: int | None = None
    login_timeout: int | None = None
    charset: str | None = None
    as_dict: bool | None = None
    host: str | None = None
    appname: str | None = None
    port: str | None = None
    conn_properties: str | None = None
    autocommit: bool | None = None
    tds_version: str | None = None


class _PyMSSQLDatabaseApiIntegration(dbapi.DatabaseApiIntegration):
    def wrapped_connection(
        self,
        connect_method: Callable[..., Any],
        args: tuple[Any, Any],
        kwargs: dict[Any, Any],
    ):
        """Add object proxy to connection object."""
        connection = connect_method(*args, **kwargs)
        connect_method_args = _PyMSSQLConnectMethodArgsTuple(*args)

        self.name = self.database_system
        self.database = kwargs.get("database") or connect_method_args.database

        user = kwargs.get("user") or connect_method_args.user
        if user is not None:
            self.span_attributes["db.user"] = user

        port = kwargs.get("port") or connect_method_args.port
        host = kwargs.get("server") or connect_method_args.server
        if host is None:
            host = kwargs.get("host") or connect_method_args.host
        if host is not None:
            # The host string can include the port, separated by either a coma or
            # a column
            for sep in (":", ","):
                if sep in host:
                    tokens = host.rsplit(sep)
                    host = tokens[0]
                    if len(tokens) > 1:
                        port = tokens[1]
        if host is not None:
            self.span_attributes["net.peer.name"] = host
        if port is not None:
            self.span_attributes["net.peer.port"] = port

        charset = kwargs.get("charset") or connect_method_args.charset
        if charset is not None:
            self.span_attributes["db.charset"] = charset

        tds_version = (
            kwargs.get("tds_version") or connect_method_args.tds_version
        )
        if tds_version is not None:
            self.span_attributes["db.protocol.tds.version"] = tds_version

        return dbapi.get_traced_connection_proxy(connection, self)


class PyMSSQLInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Integrate with the pymssql library.
        https://github.com/pymssql/pymssql/
        """
        tracer_provider = kwargs.get("tracer_provider")

        dbapi.wrap_connect(
            __name__,
            pymssql,
            "connect",
            _DATABASE_SYSTEM,
            version=__version__,
            tracer_provider=tracer_provider,
            # pymssql does not keep the connection attributes in its connection object;
            # instead, we get the attributes from the connect method (which is done
            # via PyMSSQLDatabaseApiIntegration.wrapped_connection)
            db_api_integration_factory=_PyMSSQLDatabaseApiIntegration,
        )

    def _uninstrument(self, **kwargs):
        """ "Disable pymssql instrumentation"""
        dbapi.unwrap_connect(pymssql, "connect")

    @staticmethod
    def instrument_connection(connection, tracer_provider=None):
        """Enable instrumentation in a pymssql connection.

        Args:
            connection: The connection to instrument.
            tracer_provider: The optional tracer provider to use. If omitted
                the current globally configured one is used.

        Returns:
            An instrumented connection.
        """

        return dbapi.instrument_connection(
            __name__,
            connection,
            _DATABASE_SYSTEM,
            version=__version__,
            tracer_provider=tracer_provider,
            db_api_integration_factory=_PyMSSQLDatabaseApiIntegration,
        )

    @staticmethod
    def uninstrument_connection(connection):
        """Disable instrumentation in a pymssql connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return dbapi.uninstrument_connection(connection)
