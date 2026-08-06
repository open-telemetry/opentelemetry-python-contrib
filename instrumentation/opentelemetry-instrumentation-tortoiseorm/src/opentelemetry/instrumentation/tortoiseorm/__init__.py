# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrument tortoise-orm to report SQL queries.

Usage
-----

.. code:: python

    from fastapi import FastAPI
    from tortoise.contrib.fastapi import register_tortoise
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.instrumentation.tortoiseorm import TortoiseORMInstrumentor

    app = FastAPI()
    tracer = TracerProvider(resource=Resource({SERVICE_NAME: "FastAPI"}))
    TortoiseORMInstrumentor().instrument(tracer_provider=tracer)

    register_tortoise(
        app,
        db_url="sqlite://sample.db",
        modules={"models": ["example_app.db_models"]}
    )

API
---
"""

from typing import Collection

import wrapt

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_old,
    _set_db_name,
    _set_db_query_parameters,
    _set_db_statement,
    _set_db_system,
    _set_db_user,
    _set_http_net_peer_name_client,
    _set_http_peer_port_client,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.tortoiseorm.package import _instruments
from opentelemetry.instrumentation.tortoiseorm.version import __version__
from opentelemetry.instrumentation.utils import (
    is_instrumentation_enabled,
    unwrap,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DbSystemValues,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode

try:
    import tortoise.backends.asyncpg.client

    TORTOISE_POSTGRES_SUPPORT = True
except ModuleNotFoundError:
    TORTOISE_POSTGRES_SUPPORT = False

try:
    import tortoise.backends.mysql.client

    TORTOISE_MYSQL_SUPPORT = True
except ModuleNotFoundError:
    TORTOISE_MYSQL_SUPPORT = False

try:
    import tortoise.backends.sqlite.client

    TORTOISE_SQLITE_SUPPORT = True
except ModuleNotFoundError:
    TORTOISE_SQLITE_SUPPORT = False

import tortoise.contrib.pydantic.base


class TortoiseORMInstrumentor(BaseInstrumentor):
    """An instrumentor for Tortoise-ORM
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments Tortoise ORM backend methods.
        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
                ``capture_parameters``: set to True to capture SQL query parameters
        Returns:
            None
        """
        _OpenTelemetrySemanticConventionStability._initialize()
        self._sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE
        )
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=_get_schema_url_for_signal_types(
                [_OpenTelemetryStabilitySignalType.DATABASE]
            ),
        )
        self.capture_parameters = kwargs.get("capture_parameters", False)
        if TORTOISE_SQLITE_SUPPORT:
            funcs = [
                "SqliteClient.execute_many",
                "SqliteClient.execute_query",
                "SqliteClient.execute_insert",
                "SqliteClient.execute_query_dict",
                "SqliteClient.execute_script",
            ]
            for func in funcs:
                wrapt.wrap_function_wrapper(
                    "tortoise.backends.sqlite.client",
                    func,
                    self._do_execute,
                )

        if TORTOISE_POSTGRES_SUPPORT:
            funcs = [
                "AsyncpgDBClient.execute_many",
                "AsyncpgDBClient.execute_query",
                "AsyncpgDBClient.execute_insert",
                "AsyncpgDBClient.execute_query_dict",
                "AsyncpgDBClient.execute_script",
            ]
            for func in funcs:
                wrapt.wrap_function_wrapper(
                    "tortoise.backends.asyncpg.client",
                    func,
                    self._do_execute,
                )

        if TORTOISE_MYSQL_SUPPORT:
            funcs = [
                "MySQLClient.execute_many",
                "MySQLClient.execute_query",
                "MySQLClient.execute_insert",
                "MySQLClient.execute_query_dict",
                "MySQLClient.execute_script",
            ]
            for func in funcs:
                wrapt.wrap_function_wrapper(
                    "tortoise.backends.mysql.client",
                    func,
                    self._do_execute,
                )
        wrapt.wrap_function_wrapper(
            "tortoise.contrib.pydantic.base",
            "PydanticModel.from_queryset",
            self._from_queryset,
        )
        wrapt.wrap_function_wrapper(
            "tortoise.contrib.pydantic.base",
            "PydanticModel.from_queryset_single",
            self._from_queryset,
        )
        wrapt.wrap_function_wrapper(
            "tortoise.contrib.pydantic.base",
            "PydanticListModel.from_queryset",
            self._from_queryset,
        )

    def _uninstrument(self, **kwargs):
        if TORTOISE_SQLITE_SUPPORT:
            unwrap(
                tortoise.backends.sqlite.client.SqliteClient, "execute_query"
            )
            unwrap(
                tortoise.backends.sqlite.client.SqliteClient, "execute_many"
            )
            unwrap(
                tortoise.backends.sqlite.client.SqliteClient, "execute_insert"
            )
            unwrap(
                tortoise.backends.sqlite.client.SqliteClient,
                "execute_query_dict",
            )
            unwrap(
                tortoise.backends.sqlite.client.SqliteClient, "execute_script"
            )
        if TORTOISE_MYSQL_SUPPORT:
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_query")
            unwrap(tortoise.backends.mysql.client.MySQLClient, "execute_many")
            unwrap(
                tortoise.backends.mysql.client.MySQLClient, "execute_insert"
            )
            unwrap(
                tortoise.backends.mysql.client.MySQLClient,
                "execute_query_dict",
            )
            unwrap(
                tortoise.backends.mysql.client.MySQLClient, "execute_script"
            )
        if TORTOISE_POSTGRES_SUPPORT:
            unwrap(
                tortoise.backends.asyncpg.client.AsyncpgDBClient,
                "execute_query",
            )
            unwrap(
                tortoise.backends.asyncpg.client.AsyncpgDBClient,
                "execute_many",
            )
            unwrap(
                tortoise.backends.asyncpg.client.AsyncpgDBClient,
                "execute_insert",
            )
            unwrap(
                tortoise.backends.asyncpg.client.AsyncpgDBClient,
                "execute_query_dict",
            )
            unwrap(
                tortoise.backends.asyncpg.client.AsyncpgDBClient,
                "execute_script",
            )
        unwrap(tortoise.contrib.pydantic.base.PydanticModel, "from_queryset")
        unwrap(
            tortoise.contrib.pydantic.base.PydanticModel,
            "from_queryset_single",
        )
        unwrap(
            tortoise.contrib.pydantic.base.PydanticListModel, "from_queryset"
        )

    def _hydrate_span_from_args(
        self, connection, query, parameters, is_batch: bool
    ) -> dict:
        """Get network and database attributes from connection."""
        span_attributes = {}
        mode = self._sem_conv_opt_in_mode

        capabilities = getattr(connection, "capabilities", None)
        if capabilities is not None:
            if capabilities.dialect == "sqlite":
                _set_db_system(
                    span_attributes, DbSystemValues.SQLITE.value, mode
                )
            elif capabilities.dialect == "postgres":
                _set_db_system(
                    span_attributes, DbSystemValues.POSTGRESQL.value, mode
                )
            elif capabilities.dialect == "mysql":
                _set_db_system(
                    span_attributes, DbSystemValues.MYSQL.value, mode
                )

        dbname = getattr(connection, "filename", None)
        if dbname:
            _set_db_name(span_attributes, dbname, mode)
        dbname = getattr(connection, "database", None)
        if dbname:
            _set_db_name(span_attributes, dbname, mode)

        if query is not None:
            _set_db_statement(span_attributes, query, mode)

        user = getattr(connection, "user", None)
        if user:
            _set_db_user(span_attributes, user, mode)

        host = getattr(connection, "host", None)
        if host:
            _set_http_net_peer_name_client(span_attributes, host, mode)

        port = getattr(connection, "port", None)
        if port:
            _set_http_peer_port_client(span_attributes, port, mode)

        if self.capture_parameters and parameters:
            if _report_old(mode):
                span_attributes["db.statement.parameters"] = str(parameters)
            # db.query.parameter.<key> SHOULD NOT be captured on batch
            # operations (e.g. execute_many).
            if not is_batch:
                _set_db_query_parameters(span_attributes, parameters[0], mode)

        return span_attributes

    async def _do_execute(self, func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return await func(*args, **kwargs)

        exception = None
        name = args[0].split()[0]
        is_batch = func.__name__ == "execute_many"

        with self._tracer.start_as_current_span(
            name, kind=SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span_attributes = self._hydrate_span_from_args(
                    instance,
                    args[0],
                    args[1:],
                    is_batch,
                )
                for attribute, value in span_attributes.items():
                    span.set_attribute(attribute, value)

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                raise
            finally:
                if span.is_recording() and exception is not None:
                    span.set_status(Status(StatusCode.ERROR))

        return result

    async def _from_queryset(self, func, modelcls, args, kwargs):
        if not is_instrumentation_enabled():
            return await func(*args, **kwargs)

        exception = None
        name = f"pydantic.{func.__name__}"

        with self._tracer.start_as_current_span(
            name,
            kind=SpanKind.INTERNAL,
        ) as span:
            if span.is_recording():
                span_attributes = {}

                model_config = getattr(modelcls, "Config", None)
                if model_config:
                    model_title = getattr(
                        modelcls.Config,
                        "title",
                        modelcls.__name__,
                    )
                    if model_title:
                        span_attributes["pydantic.model"] = model_title

                for attribute, value in span_attributes.items():
                    span.set_attribute(attribute, value)

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                raise
            finally:
                if span.is_recording() and exception is not None:
                    span.set_status(Status(StatusCode.ERROR))

        return result
