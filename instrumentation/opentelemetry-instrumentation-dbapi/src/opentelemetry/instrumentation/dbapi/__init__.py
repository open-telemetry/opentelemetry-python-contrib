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
The trace integration with Database API supports libraries that follow the
Python Database API Specification v2.0.
`<https://www.python.org/dev/peps/pep-0249/>`_

Usage
-----

.. code-block:: python

    import mysql.connector
    import pyodbc

    from opentelemetry.instrumentation.dbapi import trace_integration


    # Ex: mysql.connector
    trace_integration(mysql.connector, "connect", "mysql")
    # Ex: pyodbc
    trace_integration(pyodbc, "Connection", "odbc")

API
---
"""

from __future__ import annotations

import functools
import logging
import re
from typing import Any, Callable, Generic, TypeVar

import wrapt
from wrapt import wrap_function_wrapper

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.dbapi.version import __version__
from opentelemetry.instrumentation.sqlcommenter_utils import _add_sql_comment
from opentelemetry.instrumentation.utils import (
    _get_opentelemetry_values,
    unwrap,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, TracerProvider, get_tracer
from opentelemetry.util._importlib_metadata import version as util_version

_DB_DRIVER_ALIASES = {
    "MySQLdb": "mysqlclient",
}

_logger = logging.getLogger(__name__)

ConnectionT = TypeVar("ConnectionT")
CursorT = TypeVar("CursorT")


def trace_integration(
    connect_module: Callable[..., Any],
    connect_method_name: str,
    database_system: str,
    connection_attributes: dict[str, Any] | None = None,
    tracer_provider: TracerProvider | None = None,
    capture_parameters: bool = False,
    enable_commenter: bool = False,
    db_api_integration_factory: type[DatabaseApiIntegration] | None = None,
    enable_attribute_commenter: bool = False,
):
    """Integrate with DB API library.
    https://www.python.org/dev/peps/pep-0249/

    Args:
        connect_module: Module name where connect method is available.
        connect_method_name: The connect method name.
        database_system: An identifier for the database management system (DBMS)
            product being used.
        connection_attributes: Attribute names for database, port, host and
            user in Connection object.
        tracer_provider: The :class:`opentelemetry.trace.TracerProvider` to
            use. If omitted the current configured one is used.
        capture_parameters: Configure if db.statement.parameters should be captured.
        enable_commenter: Flag to enable/disable sqlcommenter.
        db_api_integration_factory: The `DatabaseApiIntegration` to use. If none is passed the
            default one is used.
        enable_attribute_commenter: Flag to enable/disable sqlcomment inclusion in `db.statement` span attribute. Only available if enable_commenter=True.
    """
    wrap_connect(
        __name__,
        connect_module,
        connect_method_name,
        database_system,
        connection_attributes,
        version=__version__,
        tracer_provider=tracer_provider,
        capture_parameters=capture_parameters,
        enable_commenter=enable_commenter,
        db_api_integration_factory=db_api_integration_factory,
        enable_attribute_commenter=enable_attribute_commenter,
    )


def wrap_connect(
    name: str,
    connect_module: Callable[..., Any],
    connect_method_name: str,
    database_system: str,
    connection_attributes: dict[str, Any] | None = None,
    version: str = "",
    tracer_provider: TracerProvider | None = None,
    capture_parameters: bool = False,
    enable_commenter: bool = False,
    db_api_integration_factory: type[DatabaseApiIntegration] | None = None,
    commenter_options: dict[str, Any] | None = None,
    enable_attribute_commenter: bool = False,
):
    """Integrate with DB API library.
    https://www.python.org/dev/peps/pep-0249/

    Args:
        connect_module: Module name where connect method is available.
        connect_method_name: The connect method name.
        database_system: An identifier for the database management system (DBMS)
            product being used.
        connection_attributes: Attribute names for database, port, host and
            user in Connection object.
        tracer_provider: The :class:`opentelemetry.trace.TracerProvider` to
            use. If omitted the current configured one is used.
        capture_parameters: Configure if db.statement.parameters should be captured.
        enable_commenter: Flag to enable/disable sqlcommenter.
        db_api_integration_factory: The `DatabaseApiIntegration` to use. If none is passed the
            default one is used.
        commenter_options: Configurations for tags to be appended at the sql query.
        enable_attribute_commenter: Flag to enable/disable sqlcomment inclusion in `db.statement` span attribute. Only available if enable_commenter=True.

    """
    db_api_integration_factory = (
        db_api_integration_factory or DatabaseApiIntegration
    )

    # pylint: disable=unused-argument
    def wrap_connect_(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, Any],
        kwargs: dict[Any, Any],
    ):
        db_integration = db_api_integration_factory(
            name,
            database_system,
            connection_attributes=connection_attributes,
            version=version,
            tracer_provider=tracer_provider,
            capture_parameters=capture_parameters,
            enable_commenter=enable_commenter,
            commenter_options=commenter_options,
            connect_module=connect_module,
            enable_attribute_commenter=enable_attribute_commenter,
        )
        return db_integration.wrapped_connection(wrapped, args, kwargs)

    try:
        wrap_function_wrapper(
            connect_module, connect_method_name, wrap_connect_
        )
    except Exception as ex:  # pylint: disable=broad-except
        _logger.warning("Failed to integrate with DB API. %s", str(ex))


def unwrap_connect(
    connect_module: Callable[..., Any], connect_method_name: str
):
    """Disable integration with DB API library.
    https://www.python.org/dev/peps/pep-0249/

    Args:
        connect_module: Module name where the connect method is available.
        connect_method_name: The connect method name.
    """
    unwrap(connect_module, connect_method_name)


def instrument_connection(
    name: str,
    connection: ConnectionT | TracedConnectionProxy[ConnectionT],
    database_system: str,
    connection_attributes: dict[str, Any] | None = None,
    version: str = "",
    tracer_provider: TracerProvider | None = None,
    capture_parameters: bool = False,
    enable_commenter: bool = False,
    commenter_options: dict[str, Any] | None = None,
    connect_module: Callable[..., Any] | None = None,
    enable_attribute_commenter: bool = False,
    db_api_integration_factory: type[DatabaseApiIntegration] | None = None,
) -> TracedConnectionProxy[ConnectionT]:
    """Enable instrumentation in a database connection.

    Args:
        name: The instrumentation module name.
        connection: The connection to instrument.
        database_system: An identifier for the database management system (DBMS)
            product being used.
        connection_attributes: Attribute names for database, port, host and
            user in a connection object.
        tracer_provider: The :class:`opentelemetry.trace.TracerProvider` to
            use. If omitted the current configured one is used.
        capture_parameters: Configure if db.statement.parameters should be captured.
        enable_commenter: Flag to enable/disable sqlcommenter.
        commenter_options: Configurations for tags to be appended at the sql query.
        connect_module: Module name where connect method is available.
        enable_attribute_commenter: Flag to enable/disable sqlcomment inclusion in `db.statement` span attribute. Only available if enable_commenter=True.
        db_api_integration_factory: A class or factory function to use as a
            replacement for :class:`DatabaseApiIntegration`. Can be used to
            obtain connection attributes from the connect method instead of
            from the connection itself (as done by the pymssql intrumentor).

    Returns:
        An instrumented connection.
    """
    if isinstance(connection, wrapt.ObjectProxy):
        _logger.warning("Connection already instrumented")
        return connection

    db_api_integration_factory = (
        db_api_integration_factory or DatabaseApiIntegration
    )

    db_integration = db_api_integration_factory(
        name,
        database_system,
        connection_attributes=connection_attributes,
        version=version,
        tracer_provider=tracer_provider,
        capture_parameters=capture_parameters,
        enable_commenter=enable_commenter,
        commenter_options=commenter_options,
        connect_module=connect_module,
        enable_attribute_commenter=enable_attribute_commenter,
    )
    db_integration.get_connection_attributes(connection)
    return get_traced_connection_proxy(connection, db_integration)


def uninstrument_connection(
    connection: ConnectionT | TracedConnectionProxy[ConnectionT],
) -> ConnectionT:
    """Disable instrumentation in a database connection.

    Args:
        connection: The connection to uninstrument.

    Returns:
        An uninstrumented connection.
    """
    if isinstance(connection, wrapt.ObjectProxy):
        return connection.__wrapped__

    _logger.warning("Connection is not instrumented")
    return connection


class DatabaseApiIntegration:
    def __init__(
        self,
        name: str,
        database_system: str,
        connection_attributes: dict[str, Any] | None = None,
        version: str = "",
        tracer_provider: TracerProvider | None = None,
        capture_parameters: bool = False,
        enable_commenter: bool = False,
        commenter_options: dict[str, Any] | None = None,
        connect_module: Callable[..., Any] | None = None,
        enable_attribute_commenter: bool = False,
    ):
        if connection_attributes is None:
            self.connection_attributes = {
                "database": "database",
                "port": "port",
                "host": "host",
                "user": "user",
            }
        else:
            self.connection_attributes = connection_attributes
        self._name = name
        self._version = version
        self._tracer = get_tracer(
            self._name,
            instrumenting_library_version=self._version,
            tracer_provider=tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        self.capture_parameters = capture_parameters
        self.enable_commenter = enable_commenter
        self.commenter_options = commenter_options
        self.enable_attribute_commenter = enable_attribute_commenter
        self.database_system = database_system
        self.connection_props: dict[str, Any] = {}
        self.span_attributes: dict[str, Any] = {}
        self.name = ""
        self.database = ""
        self.connect_module = connect_module
        self.commenter_data = self.calculate_commenter_data()

    def _get_db_version(self, db_driver: str) -> str:
        if db_driver in _DB_DRIVER_ALIASES:
            return util_version(_DB_DRIVER_ALIASES[db_driver])
        db_version = ""
        try:
            db_version = self.connect_module.__version__
        except AttributeError:
            db_version = "unknown"
        return db_version

    def calculate_commenter_data(self) -> dict[str, Any]:
        commenter_data: dict[str, Any] = {}
        if not self.enable_commenter:
            return commenter_data

        db_driver = getattr(self.connect_module, "__name__", "unknown")
        db_version = self._get_db_version(db_driver)

        commenter_data = {
            "db_driver": f"{db_driver}:{db_version.split(' ')[0]}",
            # PEP 249-compliant drivers should have the following attributes.
            # We can assume apilevel "1.0" if not given.
            # We use "unknown" for others to prevent uncaught AttributeError.
            # https://peps.python.org/pep-0249/#globals
            "dbapi_threadsafety": getattr(
                self.connect_module, "threadsafety", "unknown"
            ),
            "dbapi_level": getattr(self.connect_module, "apilevel", "1.0"),
            "driver_paramstyle": getattr(
                self.connect_module, "paramstyle", "unknown"
            ),
        }

        if self.database_system == "postgresql":
            if hasattr(self.connect_module, "__libpq_version__"):
                libpq_version = self.connect_module.__libpq_version__
            else:
                libpq_version = self.connect_module.pq.__build_version__
            commenter_data.update({"libpq_version": libpq_version})
        elif self.database_system == "mysql":
            mysqlc_version = ""
            if db_driver == "MySQLdb":
                mysqlc_version = self.connect_module._mysql.get_client_info()
            elif db_driver == "pymysql":
                mysqlc_version = self.connect_module.get_client_info()

            commenter_data.update({"mysql_client_version": mysqlc_version})

        return commenter_data

    def wrapped_connection(
        self,
        connect_method: Callable[..., ConnectionT],
        args: tuple[Any, ...],
        kwargs: dict[Any, Any],
    ) -> TracedConnectionProxy[ConnectionT]:
        """Add object proxy to connection object."""
        connection = connect_method(*args, **kwargs)
        self.get_connection_attributes(connection)
        return get_traced_connection_proxy(connection, self)

    def get_connection_attributes(self, connection: object) -> None:
        # Populate span fields using connection
        for key, value in self.connection_attributes.items():
            # Allow attributes nested in connection object
            attribute = functools.reduce(
                lambda attribute, attribute_value: getattr(
                    attribute, attribute_value, None
                ),
                value.split("."),
                connection,
            )
            if attribute:
                self.connection_props[key] = attribute
        self.name = self.database_system
        self.database = self.connection_props.get("database", "")
        if self.database:
            # PyMySQL encodes names with utf-8
            if hasattr(self.database, "decode"):
                self.database = self.database.decode(errors="ignore")
            self.name += "." + self.database
        user = self.connection_props.get("user")
        # PyMySQL encodes this data
        if user and isinstance(user, bytes):
            user = user.decode()
        if user is not None:
            self.span_attributes[SpanAttributes.DB_USER] = str(user)
        host = self.connection_props.get("host")
        if host is not None:
            self.span_attributes[SpanAttributes.NET_PEER_NAME] = host
        port = self.connection_props.get("port")
        if port is not None:
            self.span_attributes[SpanAttributes.NET_PEER_PORT] = port


# pylint: disable=abstract-method
class TracedConnectionProxy(wrapt.ObjectProxy, Generic[ConnectionT]):
    # pylint: disable=unused-argument
    def __init__(
        self,
        connection: ConnectionT,
        db_api_integration: DatabaseApiIntegration | None = None,
    ):
        wrapt.ObjectProxy.__init__(self, connection)
        self._self_db_api_integration = db_api_integration

    def __getattribute__(self, name: str):
        if object.__getattribute__(self, name):
            return object.__getattribute__(self, name)

        return object.__getattribute__(
            object.__getattribute__(self, "_connection"), name
        )

    def cursor(self, *args: Any, **kwargs: Any):
        return get_traced_cursor_proxy(
            self.__wrapped__.cursor(*args, **kwargs),
            self._self_db_api_integration,
        )

    def __enter__(self):
        self.__wrapped__.__enter__()
        return self

    def __exit__(self, *args: Any, **kwargs: Any):
        self.__wrapped__.__exit__(*args, **kwargs)


def get_traced_connection_proxy(
    connection: ConnectionT,
    db_api_integration: DatabaseApiIntegration | None,
    *args: Any,
    **kwargs: Any,
) -> TracedConnectionProxy[ConnectionT]:
    return TracedConnectionProxy(connection, db_api_integration)


class CursorTracer(Generic[CursorT]):
    def __init__(self, db_api_integration: DatabaseApiIntegration) -> None:
        self._db_api_integration = db_api_integration
        self._commenter_enabled = self._db_api_integration.enable_commenter
        self._commenter_options = (
            self._db_api_integration.commenter_options
            if self._db_api_integration.commenter_options
            else {}
        )
        self._enable_attribute_commenter = (
            self._db_api_integration.enable_attribute_commenter
        )
        self._connect_module = self._db_api_integration.connect_module
        self._leading_comment_remover = re.compile(r"^/\*.*?\*/")

    def _capture_mysql_version(self, cursor) -> None:
        """Lazy capture of mysql-connector client version using cursor, if applicable"""
        if (
            self._db_api_integration.database_system == "mysql"
            and self._db_api_integration.connect_module.__name__
            == "mysql.connector"
            and not self._db_api_integration.commenter_data[
                "mysql_client_version"
            ]
        ):
            self._db_api_integration.commenter_data["mysql_client_version"] = (
                cursor._cnx._cmysql.get_client_info()
            )

    def _get_commenter_data(self) -> dict:
        """Uses DB-API integration to return commenter data for sqlcomment"""
        commenter_data = dict(self._db_api_integration.commenter_data)
        if self._commenter_options.get("opentelemetry_values", True):
            commenter_data.update(**_get_opentelemetry_values())
        return {
            k: v
            for k, v in commenter_data.items()
            if self._commenter_options.get(k, True)
        }

    def _update_args_with_added_sql_comment(self, args, cursor) -> tuple:
        """Updates args with cursor info and adds sqlcomment to query statement"""
        try:
            args_list = list(args)
            self._capture_mysql_version(cursor)
            commenter_data = self._get_commenter_data()
            statement = _add_sql_comment(args_list[0], **commenter_data)
            args_list[0] = statement
            args = tuple(args_list)
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception(
                "Exception while generating sql comment: %s", exc
            )
        return args

    def _populate_span(
        self,
        span: trace_api.Span,
        cursor: CursorT,
        *args: tuple[Any, ...],
    ):
        if not span.is_recording():
            return
        statement = self.get_statement(cursor, args)
        span.set_attribute(
            SpanAttributes.DB_SYSTEM, self._db_api_integration.database_system
        )
        span.set_attribute(
            SpanAttributes.DB_NAME, self._db_api_integration.database
        )
        span.set_attribute(SpanAttributes.DB_STATEMENT, statement)

        for (
            attribute_key,
            attribute_value,
        ) in self._db_api_integration.span_attributes.items():
            span.set_attribute(attribute_key, attribute_value)

        if self._db_api_integration.capture_parameters and len(args) > 1:
            span.set_attribute("db.statement.parameters", str(args[1]))

    def get_operation_name(
        self, cursor: CursorT, args: tuple[Any, ...]
    ) -> str:  # pylint: disable=no-self-use
        if args and isinstance(args[0], str):
            # Strip leading comments so we get the operation name.
            return self._leading_comment_remover.sub("", args[0]).split()[0]
        return ""

    def get_statement(self, cursor: CursorT, args: tuple[Any, ...]):  # pylint: disable=no-self-use
        if not args:
            return ""
        statement = args[0]
        if isinstance(statement, bytes):
            return statement.decode("utf8", "replace")
        return statement

    def traced_execution(
        self,
        cursor: CursorT,
        query_method: Callable[..., Any],
        *args: tuple[Any, ...],
        **kwargs: dict[Any, Any],
    ):
        name = self.get_operation_name(cursor, args)
        if not name:
            name = (
                self._db_api_integration.database
                if self._db_api_integration.database
                else self._db_api_integration.name
            )

        with self._db_api_integration._tracer.start_as_current_span(
            name, kind=SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                if args and self._commenter_enabled:
                    if self._enable_attribute_commenter:
                        # sqlcomment is added to executed query and db.statement span attribute
                        args = self._update_args_with_added_sql_comment(
                            args, cursor
                        )
                        self._populate_span(span, cursor, *args)
                    else:
                        # sqlcomment is only added to executed query
                        # so db.statement is set before add_sql_comment
                        self._populate_span(span, cursor, *args)
                        args = self._update_args_with_added_sql_comment(
                            args, cursor
                        )
                else:
                    # no sqlcomment anywhere
                    self._populate_span(span, cursor, *args)
            return query_method(*args, **kwargs)


# pylint: disable=abstract-method
class TracedCursorProxy(wrapt.ObjectProxy, Generic[CursorT]):
    # pylint: disable=unused-argument
    def __init__(
        self,
        cursor: CursorT,
        db_api_integration: DatabaseApiIntegration,
    ):
        wrapt.ObjectProxy.__init__(self, cursor)
        self._self_cursor_tracer = CursorTracer[CursorT](db_api_integration)

    def execute(self, *args: Any, **kwargs: Any):
        return self._self_cursor_tracer.traced_execution(
            self.__wrapped__, self.__wrapped__.execute, *args, **kwargs
        )

    def executemany(self, *args: Any, **kwargs: Any):
        return self._self_cursor_tracer.traced_execution(
            self.__wrapped__, self.__wrapped__.executemany, *args, **kwargs
        )

    def callproc(self, *args: Any, **kwargs: Any):
        return self._self_cursor_tracer.traced_execution(
            self.__wrapped__, self.__wrapped__.callproc, *args, **kwargs
        )

    def __enter__(self):
        self.__wrapped__.__enter__()
        return self

    def __exit__(self, *args, **kwargs):
        self.__wrapped__.__exit__(*args, **kwargs)


def get_traced_cursor_proxy(
    cursor: CursorT,
    db_api_integration: DatabaseApiIntegration,
    *args: Any,
    **kwargs: Any,
) -> TracedCursorProxy[CursorT]:
    return TracedCursorProxy(cursor, db_api_integration)
