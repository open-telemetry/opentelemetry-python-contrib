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

API
---
"""

from typing import Collection

import pymysql

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.pymysql.package import _instruments
from opentelemetry.instrumentation.pymysql.version import __version__

from opentelemetry.metrics import get_meter
from opentelemetry.semconv.metrics import MetricInstruments


_CONNECTION_ATTRIBUTES = {
    "database": "db",
    "port": "port",
    "host": "host",
    "user": "user",
}
_DATABASE_SYSTEM = "mysql"


class PyMySQLInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Integrate with the PyMySQL library.
        https://github.com/PyMySQL/PyMySQL/
        """
        tracer_provider = kwargs.get("tracer_provider")

        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(__name__, __version__, meter_provider)

        createtime_histogram = meter.create_histogram(
            name=MetricInstruments.db.client.connections.create_time,
            description="The time it took to create a new connection",
            unit="ms",
        )

        pending_requests_updowncounter = meter.create_up_down_counter(
            name=MetricInstruments.db.client.connections.pending_requests,
            description="The number of pending requests for an open connection, cumulative for the entire pool.",
            unit="requests",
        )


        dbapi.wrap_connect(
            __name__,
            pymysql,
            "connect",
            _DATABASE_SYSTEM,
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            createtime_histogram=createtime_histogram,
            pending_requests_updowncounter=pending_requests_updowncounter,
        )

    def _uninstrument(self, **kwargs):
        """ "Disable PyMySQL instrumentation"""
        dbapi.unwrap_connect(pymysql, "connect")

    @staticmethod
    def instrument_connection(connection, tracer_provider=None):
        """Enable instrumentation in a PyMySQL connection.

        Args:
            connection: The connection to instrument.
            tracer_provider: The optional tracer provider to use. If omitted
                the current globally configured one is used.

        Returns:
            An instrumented connection.
        """

        meter = get_meter(__name__, __version__, PyMySQLInstrumentor.meter_provider)

        createtime_histogram = meter.create_histogram(
            name=MetricInstruments.db.client.connections.create_time,
            description="The time it took to create a new connection",
            unit="ms",
        )

        pending_requests_updowncounter = meter.create_up_down_counter(
            name=MetricInstruments.db.client.connections.pending_requests,
            description="The number of pending requests for an open connection, cumulative for the entire pool.",
            unit="requests",
        )

        connectionusage_updowncounter = meter.create_up_down_counter(
            name=MetricInstruments.db.client.connections.usage,
            description="The number of connections that are currently in state described by the state attribute",
            unit="connections",
        )


        return dbapi.instrument_connection(
            __name__,
            connection,
            _DATABASE_SYSTEM,
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            createtime_histogram=createtime_histogram,
            pending_requests_updowncounter=pending_requests_updowncounter,
            connectionusage_updowncounter=connectionusage_updowncounter,
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
