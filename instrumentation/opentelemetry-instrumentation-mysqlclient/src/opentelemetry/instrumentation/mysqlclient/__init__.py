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
    cursor.execute("INSERT INTO test (testField) VALUES (123)"
    cnx.commit()
    cursor.close()
    cnx.close()

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
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Integrate with the mysqlclient library.
        https://github.com/PyMySQL/mysqlclient/
        """
        tracer_provider = kwargs.get("tracer_provider")

        dbapi.wrap_connect(
            __name__,
            MySQLdb,
            "connect",
            _DATABASE_SYSTEM,
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
        )

    def _uninstrument(self, **kwargs):
        """ "Disable mysqlclient instrumentation"""
        dbapi.unwrap_connect(MySQLdb, "connect")

    @staticmethod
    def instrument_connection(connection, tracer_provider=None):
        """Enable instrumentation in a mysqlclient connection.

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
