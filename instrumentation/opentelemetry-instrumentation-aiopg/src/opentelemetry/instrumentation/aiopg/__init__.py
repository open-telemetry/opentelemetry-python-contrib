# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
The integration with PostgreSQL supports the aiopg library,
it can be enabled by using ``AiopgInstrumentor``.

.. aiopg: https://github.com/aio-libs/aiopg

Usage
-----

.. code-block:: python

    import asyncio
    import aiopg
    from opentelemetry.instrumentation.aiopg import AiopgInstrumentor
    # Call instrument() to wrap all database connections
    AiopgInstrumentor().instrument()

    dsn = 'user=user password=password host=127.0.0.1'

    async def connect():
        cnx = await aiopg.connect(dsn)
        cursor = await cnx.cursor()
        await cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
        await cursor.execute("INSERT INTO test (testField) VALUES (123)")
        cursor.close()
        cnx.close()

    async def create_pool():
        pool = await aiopg.create_pool(dsn)
        cnx = await pool.acquire()
        cursor = await cnx.cursor()
        await cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
        await cursor.execute("INSERT INTO test (testField) VALUES (123)")
        cursor.close()
        cnx.close()

    asyncio.run(connect())
    asyncio.run(create_pool())

.. code-block:: python

    import asyncio
    import aiopg
    from opentelemetry.instrumentation.aiopg import AiopgInstrumentor

    dsn = 'user=user password=password host=127.0.0.1'

    # Alternatively, use instrument_connection for an individual connection
    async def go():
        cnx = await aiopg.connect(dsn)
        instrumented_cnx = AiopgInstrumentor().instrument_connection(cnx)
        cursor = await instrumented_cnx.cursor()
        await cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
        await cursor.execute("INSERT INTO test (testField) VALUES (123)")
        cursor.close()
        instrumented_cnx.close()

    asyncio.run(go())

Configuration
-------------

Capture parameters
******************
By default, only statements are captured, without the associated query parameters.
To capture query parameters in the span attribute ``db.statement.parameters``, enable ``capture_parameters``.

.. code-block:: python

    from opentelemetry.instrumentation.aiopg import AiopgInstrumentor

    AiopgInstrumentor().instrument(
        capture_parameters=True,
    )

API
---
"""

from typing import Collection

from opentelemetry.instrumentation.aiopg import wrappers
from opentelemetry.instrumentation.aiopg.package import _instruments
from opentelemetry.instrumentation.aiopg.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


class AiopgInstrumentor(BaseInstrumentor):
    _CONNECTION_ATTRIBUTES = {
        "database": "info.dbname",
        "port": "info.port",
        "host": "info.host",
        "user": "info.user",
    }

    _DATABASE_SYSTEM = "postgresql"

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Integrate with PostgreSQL aiopg library.
        aiopg: https://github.com/aio-libs/aiopg
        """

        tracer_provider = kwargs.get("tracer_provider")
        capture_parameters = kwargs.get("capture_parameters", False)

        wrappers.wrap_connect(
            __name__,
            self._DATABASE_SYSTEM,
            self._CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            capture_parameters=capture_parameters,
        )

        wrappers.wrap_create_pool(
            __name__,
            self._DATABASE_SYSTEM,
            self._CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            capture_parameters=capture_parameters,
        )

    # pylint:disable=no-self-use
    def _uninstrument(self, **kwargs):
        """ "Disable aiopg instrumentation"""
        wrappers.unwrap_connect()
        wrappers.unwrap_create_pool()

    # pylint:disable=no-self-use
    def instrument_connection(
        self, connection, tracer_provider=None, capture_parameters=False
    ):
        """Enable instrumentation in a aiopg connection.

        Args:
            connection: The connection to instrument.
            tracer_provider: The optional tracer provider to use. If omitted
                the current globally configured one is used.
            capture_parameters: Configure if db.statement.parameters should
                be captured.

        Returns:
            An instrumented connection.
        """
        return wrappers.instrument_connection(
            __name__,
            connection,
            self._DATABASE_SYSTEM,
            self._CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
            capture_parameters=capture_parameters,
        )

    def uninstrument_connection(self, connection):
        """Disable instrumentation in a aiopg connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return wrappers.uninstrument_connection(connection)
