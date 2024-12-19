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
The integration with PyMySQL supports the `PyMySQL`_ library and can be enabled
by using ``PyMySQLInstrumentor``.

.. _PyMySQL: https://pypi.org/project/PyMySQL/

Usage
-----

.. code:: python

    import pymysql
    from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor

    PyMySQLInstrumentor().instrument()

    cnx = pymysql.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("INSERT INTO test (testField) VALUES (123)"
    cnx.commit()
    cursor.close()
    cnx.close()

SQLCOMMENTER
*****************************************
You can optionally configure PyMySQL instrumentation to enable sqlcommenter which enriches
the query with contextual information.

Usage
-----

.. code:: python

    import pymysql
    from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor

    PyMySQLInstrumentor().instrument(enable_commenter=True, commenter_options={})

    cnx = pymysql.connect(database="MySQL_Database")
    cursor = cnx.cursor()
    cursor.execute("INSERT INTO test (testField) VALUES (123)"
    cnx.commit()
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
Enabling this flag will add pymysql and its version, e.g. /*pymysql%%3A1.2.3*/

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
If sqlcommenter is enabled, you can optionally configure PyMySQL instrumentation to append sqlcomment to query span attribute for convenience of your platform.

.. code:: python

    from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor

    PyMySQLInstrumentor().instrument(
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

import pymysql

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.pymysql.package import _instruments
from opentelemetry.instrumentation.pymysql.version import __version__

_CONNECTION_ATTRIBUTES = {
    "database": "db",
    "port": "port",
    "host": "host",
    "user": "user",
}
_DATABASE_SYSTEM = "mysql"


class PyMySQLInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:  # pylint: disable=no-self-use
        return _instruments

    def _instrument(self, **kwargs):  # pylint: disable=no-self-use
        """Integrate with the PyMySQL library.
        https://github.com/PyMySQL/PyMySQL/
        """
        tracer_provider = kwargs.get("tracer_provider")
        enable_sqlcommenter = kwargs.get("enable_commenter", False)
        commenter_options = kwargs.get("commenter_options", {})
        enable_attribute_commenter = kwargs.get(
            "enable_attribute_commenter", False
        )

        dbapi.wrap_connect(
            __name__,
            pymysql,
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
        """ "Disable PyMySQL instrumentation"""
        dbapi.unwrap_connect(pymysql, "connect")

    @staticmethod
    def instrument_connection(
        connection,
        tracer_provider=None,
        enable_commenter=None,
        commenter_options=None,
        enable_attribute_commenter=None,
    ):
        """Enable instrumentation in a PyMySQL connection.

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
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            enable_commenter=enable_commenter,
            commenter_options=commenter_options,
            connect_module=pymysql,
            enable_attribute_commenter=enable_attribute_commenter,
        )

    @staticmethod
    def uninstrument_connection(connection):
        """Disable instrumentation in a PyMySQL connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return dbapi.uninstrument_connection(connection)
