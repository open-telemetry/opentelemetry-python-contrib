# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
SQLite instrumentation supporting `sqlite3`_, it can be enabled by
using ``SQLite3Instrumentor``. Queries made through explicit cursors and
the connection shortcut methods ``execute``, ``executemany``, and
``executescript`` are traced.

.. _sqlite3: https://docs.python.org/3/library/sqlite3.html

Usage
-----

.. code:: python

    import sqlite3
    from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

    # Call instrument() to wrap all database connections
    SQLite3Instrumentor().instrument()

    cnx = sqlite3.connect(':memory:')
    cursor = cnx.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cursor.close()
    cnx.close()

.. code:: python

    import sqlite3
    from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

    # Alternatively, use instrument_connection for an individual connection
    conn = sqlite3.connect(":memory:")
    instrumented_connection = SQLite3Instrumentor().instrument_connection(conn)
    cursor = instrumented_connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS test (testField INTEGER)")
    cursor.execute("INSERT INTO test (testField) VALUES (123)")
    cursor.execute("SELECT * FROM test")
    cursor.close()
    instrumented_connection.close()

Stable Semantic Conventions
***************************

This instrumentation supports the database semantic convention migration plan.
You can control which conventions are emitted by setting the
``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable to one of these values:

- ``database`` - emit the stable database conventions and stop emitting the
  old experimental conventions.
- ``database/dup`` - emit both the old experimental and stable database
  conventions during a transition period.
- ``http`` - emit the stable HTTP conventions and stop emitting the old
  experimental conventions.
- ``http/dup`` - emit both the old experimental and stable HTTP conventions
  during a transition period.

The environment variable accepts a comma-separated list of opt-in values. For
example, ``database,http/dup`` enables stable database conventions and emits
both old and stable HTTP conventions.

By default, when the environment variable is not set, the old experimental
database and HTTP conventions are emitted.

API
---
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Sequence
from sqlite3 import dbapi2
from typing import Any, TypeVar

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.sqlite3.package import _instruments
from opentelemetry.instrumentation.sqlite3.version import __version__
from opentelemetry.trace import TracerProvider

# No useful attributes of sqlite3 connection object
_CONNECTION_ATTRIBUTES = {}

_DATABASE_SYSTEM = "sqlite"

SQLite3Connection = TypeVar(  # pylint: disable=invalid-name
    "SQLite3Connection", bound=sqlite3.Connection | None
)


class _SQLite3ShortcutTracer(dbapi.CursorTracer[sqlite3.Connection | sqlite3.Cursor]):
    def get_operation_name(self, cursor: sqlite3.Connection | sqlite3.Cursor, args: Sequence[Any]) -> str:
        if args and isinstance(args[0], str):
            tokens = self._leading_comment_remover.sub("", args[0]).split()
            return tokens[0] if tokens else ""
        return super().get_operation_name(cursor, args)


class _SQLite3ShortcutCursorProxy(dbapi.TracedCursorProxy[sqlite3.Cursor]):
    def __init__(self, cursor: sqlite3.Cursor, db_api_integration: dbapi.DatabaseApiIntegration) -> None:
        super().__init__(cursor, db_api_integration)
        self._self_cursor_tracer = _SQLite3ShortcutTracer(db_api_integration)


class _SQLite3ConnectionProxy(dbapi.TracedConnectionProxy[sqlite3.Connection]):
    def _trace_shortcut(self, method: str, *args: Any, **kwargs: Any) -> dbapi.TracedCursorProxy[sqlite3.Cursor]:
        cursor = _SQLite3ShortcutTracer(self._self_db_api_integration).traced_execution(
            self.__wrapped__, getattr(self.__wrapped__, method), *args, **kwargs
        )
        return _SQLite3ShortcutCursorProxy(cursor, self._self_db_api_integration)

    def execute(self, *args: Any, **kwargs: Any) -> dbapi.TracedCursorProxy[sqlite3.Cursor]:
        return self._trace_shortcut("execute", *args, **kwargs)

    def executemany(self, *args: Any, **kwargs: Any) -> dbapi.TracedCursorProxy[sqlite3.Cursor]:
        return self._trace_shortcut("executemany", *args, **kwargs)

    def executescript(self, *args: Any, **kwargs: Any) -> dbapi.TracedCursorProxy[sqlite3.Cursor]:
        return self._trace_shortcut("executescript", *args, **kwargs)


class _SQLite3DatabaseApiIntegration(dbapi.DatabaseApiIntegration):
    def wrapped_connection(
        self,
        connect_method: Callable[..., sqlite3.Connection],
        args: tuple[Any, ...],
        kwargs: dict[Any, Any],
    ) -> _SQLite3ConnectionProxy:
        connection = connect_method(*args, **kwargs)
        self.get_connection_attributes(connection)
        return _SQLite3ConnectionProxy(connection, self)


class SQLite3Instrumentor(BaseInstrumentor):
    _TO_WRAP = [sqlite3, dbapi2]

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Integrate with SQLite3 Python library.
        https://docs.python.org/3/library/sqlite3.html
        """
        tracer_provider = kwargs.get("tracer_provider")

        for module in self._TO_WRAP:
            dbapi.wrap_connect(
                __name__,
                module,
                "connect",
                _DATABASE_SYSTEM,
                _CONNECTION_ATTRIBUTES,
                version=__version__,
                tracer_provider=tracer_provider,
                db_api_integration_factory=_SQLite3DatabaseApiIntegration,
            )

    def _uninstrument(self, **kwargs: Any) -> None:
        """ "Disable SQLite3 instrumentation"""
        for module in self._TO_WRAP:
            dbapi.unwrap_connect(module, "connect")

    @staticmethod
    def instrument_connection(
        connection: SQLite3Connection,
        tracer_provider: TracerProvider | None = None,
    ) -> SQLite3Connection:
        """Enable instrumentation in a SQLite connection.

        Args:
            connection: The connection to instrument.
            tracer_provider: The optional tracer provider to use. If omitted
                the current globally configured one is used.

        Returns:
            An instrumented SQLite connection that supports
            telemetry for tracing database operations.

        """
        instrumented_connection = dbapi.instrument_connection(
            __name__,
            connection,
            _DATABASE_SYSTEM,
            _CONNECTION_ATTRIBUTES,
            version=__version__,
            tracer_provider=tracer_provider,
        )
        if instrumented_connection is connection:
            return connection
        return _SQLite3ConnectionProxy(
            instrumented_connection.__wrapped__,
            instrumented_connection._self_db_api_integration,
        )

    @staticmethod
    def uninstrument_connection(
        connection: SQLite3Connection,
    ) -> SQLite3Connection:
        """Disable instrumentation in a SQLite connection.

        Args:
            connection: The connection to uninstrument.

        Returns:
            An uninstrumented connection.
        """
        return dbapi.uninstrument_connection(connection)
