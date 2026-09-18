# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
This library provides tracing for the `python-oracledb`_ database driver.

Installation
------------

::

    pip install opentelemetry-instrumentation-oracledb

Usage
-----

Call ``OracleDBInstrumentor.instrument()`` before creating connections to
instrument both the synchronous and asynchronous connection factories:

.. code-block:: python

    import oracledb

    from opentelemetry.instrumentation.oracledb import OracleDBInstrumentor

    OracleDBInstrumentor().instrument()

    connection = oracledb.connect(
        user="system",
        password="password",
        dsn="localhost:1521/FREEPDB1",
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM dual")

Existing synchronous connections can be instrumented individually:

.. code-block:: python

    connection = OracleDBInstrumentor().instrument_connection(connection)

The ``opentelemetry_instrumentor`` entry point also enables discovery by the
``opentelemetry-instrument`` command.

SQLCommenter
------------

SQLCommenter can be enabled with ``enable_commenter=True``. The available
``commenter_options`` and ``enable_attribute_commenter`` settings are passed
to the shared OpenTelemetry DB API instrumentation.

API
---

.. _python-oracledb: https://python-oracledb.readthedocs.io/
"""

from __future__ import annotations

# pylint: disable=no-name-in-module, no-member
import logging
from collections.abc import Callable, Collection
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, cast

import oracledb
import oracledb.connection as _oracledb_connection_module

from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation._semconv import _report_new
from opentelemetry.instrumentation.dbapi import (
    CursorTracer,
    DatabaseApiIntegration,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.oracledb.package import _instruments
from opentelemetry.instrumentation.oracledb.version import __version__
from opentelemetry.semconv._incubating.attributes.oracle_attributes import (
    ORACLE_DB_DOMAIN,
    ORACLE_DB_INSTANCE_NAME,
    ORACLE_DB_NAME,
    ORACLE_DB_SERVICE,
)

if TYPE_CHECKING:
    from opentelemetry.instrumentation.dbapi import TracedConnectionProxy
    from opentelemetry.metrics import MeterProvider
    from opentelemetry.trace import TracerProvider

    class _BaseObjectProxy:
        __wrapped__: Any

        def __init__(self, wrapped: Any) -> None: ...

    def _wrap_function_wrapper(
        module: Callable[..., Any],
        name: str,
        wrapper: Callable[..., Any],
    ) -> None: ...

else:
    try:
        # wrapt 2.0.0+
        from wrapt import BaseObjectProxy as _BaseObjectProxy
    except ImportError:
        from wrapt import ObjectProxy as _BaseObjectProxy
    from wrapt import wrap_function_wrapper as _wrap_function_wrapper

_logger = logging.getLogger(__name__)

_DATABASE_SYSTEM = "oracle"
_DATABASE_SYSTEM_NAME = "oracle.db"

_CONNECTION_ATTRIBUTES = {
    "database": "db_name",
    "user": "username",
}

_ORACLE_CONNECTION_ATTRIBUTES = {
    ORACLE_DB_DOMAIN: "db_domain",
    ORACLE_DB_INSTANCE_NAME: "instance_name",
    ORACLE_DB_NAME: "db_name",
    ORACLE_DB_SERVICE: "service_name",
}

# python-oracledb re-exports connect and connect_async from its connection
# submodule. Wrap both references because applications may import either path.
_CONNECT_TARGETS = (
    oracledb,
    _oracledb_connection_module,
)


class _OracleDatabaseApiIntegration(DatabaseApiIntegration):
    def get_connection_attributes(self, connection: object) -> None:
        if _report_new(self._sem_conv_opt_in_mode_db):
            self.database_system = _DATABASE_SYSTEM_NAME
        super().get_connection_attributes(connection)

        # Oracle defines db.namespace as DB_UNIQUE_NAME, not DB_NAME.
        db_unique_name = getattr(connection, "db_unique_name", None)
        self.database = db_unique_name if isinstance(db_unique_name, str) and db_unique_name else ""
        self.name = self.database_system
        if self.database:
            self.name += "." + self.database

        for attribute_name, connection_attribute in _ORACLE_CONNECTION_ATTRIBUTES.items():
            value = getattr(connection, connection_attribute, None)
            if isinstance(value, str) and value:
                self.span_attributes[attribute_name] = value


# pylint: disable-next=abstract-method
class _AsyncTracedCursorProxy(_BaseObjectProxy):
    def __init__(self, cursor: Any, db_api_integration: DatabaseApiIntegration) -> None:
        super().__init__(cursor)
        self._self_cursor_tracer = CursorTracer[Any](db_api_integration)

    def __enter__(self) -> _AsyncTracedCursorProxy:
        self.__wrapped__.__enter__()
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> Any:
        return self.__wrapped__.__exit__(*args, **kwargs)

    async def __aenter__(self) -> _AsyncTracedCursorProxy:
        await self.__wrapped__.__aenter__()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.__wrapped__.__aexit__(*args, **kwargs)

    def __aiter__(self) -> Any:
        return self.__wrapped__.__aiter__()

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return await self._self_cursor_tracer.traced_execution_async(
            self.__wrapped__, self.__wrapped__.execute, *args, **kwargs
        )

    async def executemany(self, *args: Any, **kwargs: Any) -> Any:
        return await self._self_cursor_tracer.traced_execution_async(
            self.__wrapped__, self.__wrapped__.executemany, *args, **kwargs
        )

    async def callproc(self, *args: Any, **kwargs: Any) -> Any:
        return await self._self_cursor_tracer.traced_execution_async(
            self.__wrapped__, self.__wrapped__.callproc, *args, **kwargs
        )


# pylint: disable-next=abstract-method
class _AsyncTracedConnectionProxy(_BaseObjectProxy):
    def __init__(
        self,
        connection: Any,
        db_api_integration: DatabaseApiIntegration,
    ) -> None:
        super().__init__(connection)
        self._self_db_api_integration = db_api_integration

    async def __aenter__(self) -> _AsyncTracedConnectionProxy:
        connection = await self.__wrapped__.__aenter__()
        if connection is not None:
            self.__wrapped__ = connection
        self._self_db_api_integration.get_connection_attributes(self.__wrapped__)
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> Any:
        return await self.__wrapped__.__aexit__(*args, **kwargs)

    def __await__(self) -> Any:
        async def connect() -> _AsyncTracedConnectionProxy:
            if isawaitable(self.__wrapped__):
                connection = await self.__wrapped__
                if connection is not None:
                    self.__wrapped__ = connection
            self._self_db_api_integration.get_connection_attributes(self.__wrapped__)
            return self

        return connect().__await__()  # pylint: disable=no-value-for-parameter

    def cursor(self, *args: Any, **kwargs: Any) -> _AsyncTracedCursorProxy:
        cursor = self.__wrapped__.cursor(*args, **kwargs)
        return _AsyncTracedCursorProxy(
            cursor,
            self._self_db_api_integration,
        )


# pylint: disable-next=too-many-positional-arguments
def _wrap_connect_async(
    name: str,
    connect_module: Callable[..., Any],
    connect_method_name: str,
    database_system: str,
    connection_attributes: dict[str, str] | None,
    version: str,
    tracer_provider: TracerProvider | None,
    enable_commenter: bool,
    commenter_options: dict[str, Any] | None,
    enable_attribute_commenter: bool,
    meter_provider: MeterProvider | None,
) -> None:
    def wrap_connect_async_(
        wrapped: Callable[..., Any],
        _instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        integration = _OracleDatabaseApiIntegration(
            name,
            database_system,
            connection_attributes=connection_attributes,
            version=version,
            tracer_provider=tracer_provider,
            enable_commenter=enable_commenter,
            commenter_options=commenter_options,
            connect_module=connect_module,
            enable_attribute_commenter=enable_attribute_commenter,
            meter_provider=meter_provider,
        )
        connection = wrapped(*args, **kwargs)
        return _AsyncTracedConnectionProxy(connection, integration)

    try:
        _wrap_function_wrapper(
            connect_module,
            connect_method_name,
            wrap_connect_async_,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "Failed to integrate async connect with DB API. %s",
            exc,
        )


class OracleDBInstrumentor(BaseInstrumentor):
    """Instrument synchronous and asynchronous python-oracledb connections."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")
        enable_commenter = kwargs.get("enable_commenter", False)
        commenter_options = kwargs.get("commenter_options", {})
        enable_attribute_commenter = kwargs.get(
            "enable_attribute_commenter",
            False,
        )

        for target in _CONNECT_TARGETS:
            connect_module = cast(Callable[..., Any], target)
            dbapi.wrap_connect(
                __name__,
                connect_module,
                "connect",
                _DATABASE_SYSTEM,
                _CONNECTION_ATTRIBUTES,
                version=__version__,
                tracer_provider=tracer_provider,
                enable_commenter=enable_commenter,
                commenter_options=commenter_options,
                enable_attribute_commenter=enable_attribute_commenter,
                db_api_integration_factory=_OracleDatabaseApiIntegration,
                meter_provider=meter_provider,
            )
            _wrap_connect_async(
                __name__,
                connect_module,
                "connect_async",
                _DATABASE_SYSTEM,
                _CONNECTION_ATTRIBUTES,
                version=__version__,
                tracer_provider=tracer_provider,
                enable_commenter=enable_commenter,
                commenter_options=commenter_options,
                enable_attribute_commenter=enable_attribute_commenter,
                meter_provider=meter_provider,
            )

    def _uninstrument(self, **kwargs: Any) -> None:
        for target in _CONNECT_TARGETS:
            connect_module = cast(Callable[..., Any], target)
            dbapi.unwrap_connect(connect_module, "connect")
            dbapi.unwrap_connect(connect_module, "connect_async")

    # pylint: disable-next=too-many-positional-arguments
    @staticmethod
    def instrument_connection(
        connection: oracledb.Connection,
        tracer_provider: TracerProvider | None = None,
        enable_commenter: bool = False,
        commenter_options: dict[str, Any] | None = None,
        enable_attribute_commenter: bool = False,
        meter_provider: MeterProvider | None = None,
    ) -> TracedConnectionProxy[oracledb.Connection]:
        """Instrument an existing synchronous OracleDB connection.

        Args:
            connection: The OracleDB connection to instrument.
            tracer_provider: The optional tracer provider to use.
            enable_commenter: Whether to enable SQLCommenter.
            commenter_options: SQLCommenter configuration options.
            enable_attribute_commenter: Whether to add the SQL comment to
                the query span attribute.
            meter_provider: The optional meter provider to use.
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
            connect_module=cast(Callable[..., Any], oracledb),
            enable_attribute_commenter=enable_attribute_commenter,
            db_api_integration_factory=_OracleDatabaseApiIntegration,
            meter_provider=meter_provider,
        )

    @staticmethod
    def uninstrument_connection(
        connection: oracledb.Connection | TracedConnectionProxy[oracledb.Connection],
    ) -> oracledb.Connection:
        """Return the raw connection underlying an instrumented connection."""
        return dbapi.uninstrument_connection(connection)
