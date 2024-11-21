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
MySQL instrumentation supporting `mysql-connector`_, it can be enabled by
using ``MySQLInstrumentor``.

.. _mysql-connector: https://pypi.org/project/mysql-connector/

Usage
-----

.. code:: python

    import mysql.connector
    from opentelemetry.instrumentation.mysql import MySQLInstrumentor

    MySQLInstrumentor().instrument()

    cnx = mysql.connector.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cursor.close()
    cnx.close()

SQLCOMMENTER
*****************************************
You can optionally configure mysql-connector instrumentation to enable sqlcommenter which enriches
the query with contextual information.

Usage
-----

.. code:: python

    import mysql.connector
    from opentelemetry.instrumentation.mysql import MySQLInstrumentor

    MySQLInstrumentor().instrument(enable_commenter=True, commenter_options={})

    cnx = mysql.connector.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cursor.close()
    cnx.close()


For example,
::

   Invoking cursor.execute("INSERT INTO test (testField) VALUES (123)") will lead to sql query "INSERT INTO test (testField) VALUES (123)" but when SQLCommenter is enabled
   the query will get appended with some configurable tags like "INSERT INTO test (testField) VALUES (123) /*tag=value*/;"


SQLCommenter Configurations
***************************
We can configure the tags to be appended to the sqlquery log by adding configuration inside commenter_options(default:{}) keyword

db_driver = True(Default) or False

For example,
::
Enabling this flag will add mysql.connector and its version, e.g. /*mysql.connector%%3A1.2.3*/

dbapi_threadsafety = True(Default) or False

For example,
::
Enabling this flag will add threadsafety /*dbapi_threadsafety=2*/

dbapi_level = True(Default) or False

For example,
::
Enabling this flag will add dbapi_level /*dbapi_level='2.0'*/

mysql_client_version = True(Default) or False

For example,
::
Enabling this flag will add mysql_client_version /*mysql_client_version='123'*/

driver_paramstyle = True(Default) or False

For example,
::
Enabling this flag will add driver_paramstyle /*driver_paramstyle='pyformat'*/

opentelemetry_values = True(Default) or False

For example,
::
Enabling this flag will add traceparent values /*traceparent='00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01'*/

API
---
"""

import logging
import typing

import mysql.connector
import wrapt

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.mysql.package import _instruments
from opentelemetry.instrumentation.mysql.version import __version__

_logger = logging.getLogger(__name__)


class MySQLInstrumentor(BaseInstrumentor):
    _CONNECTION_ATTRIBUTES = {
        "database": "database",
        "port": "server_port",
        "host": "server_host",
        "user": "user",
    }

    _DATABASE_SYSTEM = "mysql"

    def instrumentation_dependencies(self) -> typing.Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Integrate with MySQL Connector/Python library.
        https://dev.mysql.com/doc/connector-python/en/
        """
        tracer_provider = kwargs.get("tracer_provider")
        enable_sqlcommenter = kwargs.get("enable_commenter", False)
        commenter_options = kwargs.get("commenter_options", {})

        dbapi.wrap_connect(
            __name__,
            mysql.connector,
            "connect",
            self._DATABASE_SYSTEM,
            self._CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            db_api_integration_factory=DatabaseApiIntegration,
            enable_commenter=enable_sqlcommenter,
            commenter_options=commenter_options,
        )

    def _uninstrument(self, **kwargs):
        """ "Disable MySQL instrumentation"""
        dbapi.unwrap_connect(mysql.connector, "connect")

    # pylint:disable=no-self-use
    def instrument_connection(
        self,
        connection,
        tracer_provider: typing.Optional[trace_api.TracerProvider] = None,
        enable_commenter: bool = False,
        commenter_options: dict = None,
    ):
        """Enable instrumentation in a MySQL connection.

        Args:
            connection: The connection to instrument.
            tracer_provider: The optional tracer provider to use. If omitted
                the current globally configured one is used.
            enable_commenter: Flag to enable/disable sqlcommenter.
            commenter_options: Configurations for tags to be appended at the sql query.

        Returns:
            An instrumented connection.
        """
        if isinstance(connection, wrapt.ObjectProxy):
            _logger.warning("Connection already instrumented")
            return connection

        db_integration = DatabaseApiIntegration(
            __name__,
            self._DATABASE_SYSTEM,
            self._CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            enable_commenter=enable_commenter,
            commenter_options=commenter_options,
            connect_module=mysql.connector,
        )
        db_integration.get_connection_attributes(connection)
        return get_traced_connection_proxy(connection, db_integration)

    def uninstrument_connection(
        self,
        connection,
    ):
        """Disable instrumentation in a MySQL connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return dbapi.uninstrument_connection(connection)


class DatabaseApiIntegration(dbapi.DatabaseApiIntegration):
    def wrapped_connection(
        self,
        connect_method: typing.Callable[..., typing.Any],
        args: typing.Tuple[typing.Any, typing.Any],
        kwargs: typing.Dict[typing.Any, typing.Any],
    ):
        """Add object proxy to connection object that checks cursor type."""
        connection = connect_method(*args, **kwargs)
        self.get_connection_attributes(connection)
        return get_traced_connection_proxy(connection, self)


def get_traced_connection_proxy(
    connection, db_api_integration, *args, **kwargs
):
    # pylint: disable=abstract-method
    class TracedConnectionProxy(dbapi.BaseTracedConnectionProxy):
        def cursor(self, *args, **kwargs):
            wrapped_cursor = self.__wrapped__.cursor(*args, **kwargs)

            # It's common to have multiple db client cursors per app,
            # so enable_commenter is calculated for the cursor level for
            # traced query execution.
            enable_commenter_cursor = db_api_integration.enable_commenter

            # If a mysql-connector cursor was created with prepared=True,
            # then MySQL statements will be prepared and executed natively.
            # 1:1 sqlcomment and span correlation in instrumentation would
            # break, so sqlcomment is not supported for this use case.
            # This is here because wrapped cursor is created when application
            # side creates cursor. After that, the instrumentor knows what
            # kind of cursor was initialized.
            if enable_commenter_cursor:
                is_prepared = False
                if (
                    db_api_integration.database_system == "mysql"
                    and db_api_integration.connect_module.__name__
                    == "mysql.connector"
                ):
                    is_prepared = self.is_mysql_connector_cursor_prepared(
                        wrapped_cursor
                    )
                if is_prepared:
                    _logger.warning(
                        "sqlcomment is not supported for query statements executed by cursors with native prepared statement support. Disabling sqlcommenting for instrumentation of %s.",
                        db_api_integration.connect_module.__name__,
                    )
                    enable_commenter_cursor = False
            return get_traced_cursor_proxy(
                wrapped_cursor,
                db_api_integration,
                enable_commenter_cursor,
            )

        def is_mysql_connector_cursor_prepared(self, cursor):  # pylint: disable=no-self-use
            try:
                from mysql.connector.cursor_cext import (  # pylint: disable=import-outside-toplevel
                    CMySQLCursorPrepared,
                    CMySQLCursorPreparedDict,
                    CMySQLCursorPreparedNamedTuple,
                    CMySQLCursorPreparedRaw,
                )

                if type(cursor) in [
                    CMySQLCursorPrepared,
                    CMySQLCursorPreparedDict,
                    CMySQLCursorPreparedNamedTuple,
                    CMySQLCursorPreparedRaw,
                ]:
                    return True

            except ImportError as exc:
                _logger.warning(
                    "Could not verify mysql.connector cursor, skipping prepared cursor check: %s",
                    exc,
                )

            return False

    return TracedConnectionProxy(connection, *args, **kwargs)


class CursorTracer(dbapi.CursorTracer):
    def __init__(
        self,
        db_api_integration: DatabaseApiIntegration,
        enable_commenter: bool = False,
    ) -> None:
        super().__init__(db_api_integration)
        # It's common to have multiple db client cursors per app,
        # so enable_commenter is set at the cursor level and used
        # during CursorTracer.traced_execution for mysql-connector
        self._commenter_enabled = enable_commenter


def get_traced_cursor_proxy(
    cursor, db_api_integration, enable_commenter_cursor, *args, **kwargs
):
    class TracedCursorProxy(dbapi.BaseTracedCursorProxy):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._cursor_tracer = CursorTracer(
                db_api_integration,
                enable_commenter_cursor,
            )

    return TracedCursorProxy(cursor, *args, **kwargs)
