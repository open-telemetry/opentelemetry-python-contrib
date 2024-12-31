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

SQLCOMMENTER
*****************************************
You can optionally configure Psycopg2 instrumentation to enable sqlcommenter which enriches
the query with contextual information.

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.mysql import MySQLInstrumentor()

    MySQLInstrumentor().instrument(enable_commenter=True, commenter_options={})


For example,
::

   Invoking cursor.execute("select * from auth_users") will lead to sql query "select * from auth_users" but when SQLCommenter is enabled
   the query will get appended with some configurable tags like "select * from auth_users /*tag=value*/;"


SQLCommenter Configurations
***************************
We can configure the tags to be appended to the sqlquery log by adding configuration inside commenter_options(default:{}) keyword

db_driver = True(Default) or False

For example,
::
Enabling this flag will add mysql and its version.

dbapi_threadsafety = True(Default) or False

For example,
::
Enabling this flag will add threadsafety /*dbapi_threadsafety=2*/

dbapi_level = True(Default) or False

For example,
::
Enabling this flag will add dbapi_level /*dbapi_level='2.0'*/

libpq_version = True(Default) or False

For example,
::
Enabling this flag will add libpq_version /*libpq_version=140001*/

driver_paramstyle = True(Default) or False

For example,
::
Enabling this flag will add driver_paramstyle /*driver_paramstyle='pyformat'*/

opentelemetry_values = True(Default) or False

For example,
::
Enabling this flag will add traceparent values /*traceparent='00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01'*/

Usage
-----

.. code:: python

    import mysql.connector
    from opentelemetry.instrumentation.mysql import MySQLInstrumentor

    # Call instrument() to wrap all database connections
    MySQLInstrumentor().instrument()

    cnx = mysql.connector.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cursor.close()
    cnx.close()

.. code:: python

    import mysql.connector
    from opentelemetry.instrumentation.mysql import MySQLInstrumentor

    # Alternatively, use instrument_connection for an individual connection
    cnx = mysql.connector.connect(database="MySQL_Database")
    instrumented_cnx = MySQLInstrumentor().instrument_connection(cnx)
    cursor = instrumented_cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cursor.close()
    instrumented_cnx.close()

API
---
"""

from typing import Collection

import mysql.connector

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.mysql.package import _instruments
from opentelemetry.instrumentation.mysql.version import __version__


class MySQLInstrumentor(BaseInstrumentor):
    _CONNECTION_ATTRIBUTES = {
        "database": "database",
        "port": "server_port",
        "host": "server_host",
        "user": "user",
    }

    _DATABASE_SYSTEM = "mysql"

    def instrumentation_dependencies(self) -> Collection[str]:
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
            enable_commenter=enable_sqlcommenter,
            commenter_options=commenter_options,
        )

    def _uninstrument(self, **kwargs):
        """ "Disable MySQL instrumentation"""
        dbapi.unwrap_connect(mysql.connector, "connect")

    # pylint:disable=no-self-use
    def instrument_connection(self, connection, tracer_provider=None):
        """Enable instrumentation in a MySQL connection.

        Args:
            connection:
                The existing MySQL connection instance to instrument. This connection is typically
                obtained through `mysql.connector.connect()` and is instrumented to collect telemetry
                data about database interactions.
            tracer_provider:
                An optional `TracerProvider` instance to use for tracing. If not provided, the globally
                configured tracer provider will be automatically used.

        Returns:
            An instrumented MySQL connection with OpenTelemetry tracing enabled.
        """
        return dbapi.instrument_connection(
            __name__,
            connection,
            self._DATABASE_SYSTEM,
            self._CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
        )

    def uninstrument_connection(self, connection):
        """Disable instrumentation in a MySQL connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return dbapi.uninstrument_connection(connection)
