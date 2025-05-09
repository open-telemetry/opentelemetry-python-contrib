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
The integration with MySQLClient supports the `MySQLClient`_ library and can be enabled
by using ``MySQLClientInstrumentor``.

.. _MySQLClient: https://pypi.org/project/MySQLClient/

Usage
-----

.. code:: python

    import MySQLdb
    from opentelemetry.instrumentation.mysqlclient import MySQLClientInstrumentor

    MySQLClientInstrumentor().instrument()

    cnx = MySQLdb.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cnx.commit()
    cursor.close()
    cnx.close()

SQLCOMMENTER
*****************************************
You can optionally configure MySQLClient instrumentation to enable sqlcommenter which enriches
the query with contextual information.

.. code:: python

    import MySQLdb
    from opentelemetry.instrumentation.mysqlclient import MySQLClientInstrumentor

    # Call instrument() to wrap all database connections
    MySQLClientInstrumentor().instrument(enable_commenter=True, commenter_options={})

    cnx = MySQLdb.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cnx.commit()
    cursor.close()
    cnx.close()

.. code:: python

    import MySQLdb
    from opentelemetry.instrumentation.mysqlclient import MySQLClientInstrumentor

    # Alternatively, use instrument_connection for an individual connection
    cnx = MySQLdb.connect(database="MySQL_Database")
    instrumented_cnx = MySQLClientInstrumentor().instrument_connection(
        cnx,
        enable_commenter=True,
        commenter_options={
            "db_driver": True,
            "mysql_client_version": True,
            "driver_paramstyle": False
        }
    )
    cursor = instrumented_cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    instrumented_cnx.commit()
    cursor.close()
    instrumented_cnx.close()

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
Enabling this flag will add MySQLdb and its version, e.g. /*MySQLdb%%3A1.2.3*/

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

SQLComment in span attribute
****************************
If sqlcommenter is enabled, you can optionally configure MySQLClient instrumentation to append sqlcomment to query span attribute for convenience of your platform.

.. code:: python

    from opentelemetry.instrumentation.mysqlclient import MySQLClientInstrumentor

    MySQLClientInstrumentor().instrument(
        enable_commenter=True,
        enable_attribute_commenter=True,
    )


For example,
::

    Invoking cursor.execute("select * from auth_users") will lead to sql query "select * from auth_users" but when SQLCommenter and attribute_commenter are enabled
    the query will get appended with some configurable tags like "select * from auth_users /*tag=value*/;" for both server query and `db.statement` span attribute.

API
---
"""

from typing import Collection

import MySQLdb

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.mysqlclient.package import _instruments
from opentelemetry.instrumentation.mysqlclient.version import __version__

_CONNECTION_ATTRIBUTES = {
    "database": "db",
    "port": "port",
    "host": "host",
    "user": "user",
}
_DATABASE_SYSTEM = "mysql"


class MySQLClientInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:  # pylint: disable=no-self-use
        return _instruments

    def _instrument(self, **kwargs):  # pylint: disable=no-self-use
        """Integrate with the mysqlclient library.
        https://github.com/PyMySQL/mysqlclient/
        """
        tracer_provider = kwargs.get("tracer_provider")
        enable_sqlcommenter = kwargs.get("enable_commenter", False)
        commenter_options = kwargs.get("commenter_options", {})
        enable_attribute_commenter = kwargs.get(
            "enable_attribute_commenter", False
        )

        dbapi.wrap_connect(
            __name__,
            MySQLdb,
            "connect",
            _DATABASE_SYSTEM,
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            enable_commenter=enable_sqlcommenter,
            commenter_options=commenter_options,
            enable_attribute_commenter=enable_attribute_commenter,
        )

    def _uninstrument(self, **kwargs):  # pylint: disable=no-self-use
        """ "Disable mysqlclient instrumentation"""
        dbapi.unwrap_connect(MySQLdb, "connect")

    @staticmethod
    def instrument_connection(
        connection,
        tracer_provider=None,
        enable_commenter=None,
        commenter_options=None,
        enable_attribute_commenter=None,
    ):
        """Enable instrumentation in a mysqlclient connection.

        Args:
            connection:
                The MySQL connection instance to instrument. This connection is typically
                created using `MySQLdb.connect()` and needs to be wrapped to collect telemetry.
            tracer_provider:
                A custom `TracerProvider` instance to be used for tracing. If not specified,
                the globally configured tracer provider will be used.
            enable_commenter:
                A flag to enable the OpenTelemetry SQLCommenter feature. If set to `True`,
                SQL queries will be enriched with contextual information (e.g., database client details).
                Default is `None`.
            commenter_options:
                A dictionary of configuration options for SQLCommenter. All options are enabled (True) by default.
                This allows you to customize metadata appended to queries. Possible options include:

                    - `db_driver`: Adds the database driver name and version.
                    - `dbapi_threadsafety`: Adds threadsafety information.
                    - `dbapi_level`: Adds the DB-API version.
                    - `mysql_client_version`: Adds the MySQL client version.
                    - `driver_paramstyle`: Adds the parameter style.
                    - `opentelemetry_values`: Includes traceparent values.
        Returns:
            An instrumented MySQL connection with OpenTelemetry support enabled.
        """

        return dbapi.instrument_connection(
            __name__,
            connection,
            _DATABASE_SYSTEM,
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            enable_commenter=enable_commenter,
            commenter_options=commenter_options,
            connect_module=MySQLdb,
            enable_attribute_commenter=enable_attribute_commenter,
        )

    @staticmethod
    def uninstrument_connection(connection):
        """Disable instrumentation in a mysqlclient connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return dbapi.uninstrument_connection(connection)
