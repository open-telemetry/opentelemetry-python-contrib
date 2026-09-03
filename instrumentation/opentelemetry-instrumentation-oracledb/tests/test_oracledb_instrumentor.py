# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
from contextlib import contextmanager
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import oracledb

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.dbapi import TracedConnectionProxy
from opentelemetry.instrumentation.oracledb import (
    _CONNECTION_ATTRIBUTES,
    _DATABASE_SYSTEM,
    OracleDBInstrumentor,
    _OracleDatabaseApiIntegration,
)
from opentelemetry.instrumentation.oracledb.package import _instruments
from opentelemetry.instrumentation.oracledb.version import __version__
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
    DB_USER,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
)
from opentelemetry.semconv._incubating.attributes.oracle_attributes import (
    ORACLE_DB_DOMAIN,
    ORACLE_DB_INSTANCE_NAME,
    ORACLE_DB_NAME,
    ORACLE_DB_SERVICE,
)

oracledb_connection_module = importlib.import_module("oracledb.connection")


def _make_mock_connection(
    *,
    db_name: str = "orcl",
    db_domain: str = "example.com",
    instance_name: str = "orcl1",
    service_name: str = "freepdb1",
    username: str = "scott",
) -> MagicMock:
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None

    connection = MagicMock()
    connection.db_name = db_name
    connection.db_domain = db_domain
    connection.instance_name = instance_name
    connection.service_name = service_name
    connection.username = username
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = None
    return connection


def _make_mock_async_connection(
    *,
    db_name: str = "orcl",
    db_domain: str = "example.com",
    instance_name: str = "orcl1",
    service_name: str = "freepdb1",
    username: str = "scott",
) -> MagicMock:
    cursor = MagicMock()
    cursor.execute = AsyncMock()
    cursor.executemany = AsyncMock()
    cursor.callproc = AsyncMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    cursor.__aenter__ = AsyncMock(return_value=cursor)
    cursor.__aexit__ = AsyncMock(return_value=None)

    connection = MagicMock()
    connection.db_name = db_name
    connection.db_domain = db_domain
    connection.instance_name = instance_name
    connection.service_name = service_name
    connection.username = username
    connection.cursor.return_value = cursor
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=None)
    return connection


class _OracleDBTestBase:  # pylint: disable=invalid-name
    tracer_provider: TracerProvider
    memory_exporter: InMemorySpanExporter

    def setUp(self) -> None:
        self.tracer_provider = TracerProvider()
        self.memory_exporter = InMemorySpanExporter()
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.memory_exporter))

    def tearDown(self) -> None:
        instrumentor = OracleDBInstrumentor()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        self.memory_exporter.clear()

    def _instrument(self, **kwargs) -> None:
        kwargs.setdefault("tracer_provider", self.tracer_provider)
        OracleDBInstrumentor().instrument(**kwargs)

    @contextmanager
    def _instrumented(self, **kwargs):
        self._instrument(**kwargs)
        try:
            yield
        finally:
            OracleDBInstrumentor().uninstrument()


class TestOracleDBInstrumentor(_OracleDBTestBase, TestCase):
    @staticmethod
    def _run_cursor_method(
        connect_module=oracledb,
        method: str = "execute",
        statement: str = "SELECT 1 FROM dual",
        /,
        *extra_args,
    ):
        connection = connect_module.connect(
            user="scott",
            password="tiger",
            dsn="localhost/freepdb1",
        )
        return getattr(connection.cursor(), method)(statement, *extra_args)

    def test_instrumentation_dependencies(self):
        dependencies = OracleDBInstrumentor().instrumentation_dependencies()
        self.assertEqual(dependencies, _instruments)
        self.assertEqual(dependencies, ("oracledb >= 2.0, < 5.0",))

    def test_instrument_and_uninstrument_wrap_factories(self):
        module_cases = [oracledb, oracledb_connection_module]
        factory_names = ["connect", "connect_async"]
        originals = {
            (module, factory_name): getattr(module, factory_name)
            for module in module_cases
            for factory_name in factory_names
        }

        with self._instrumented():
            for module in module_cases:
                for factory_name in factory_names:
                    with self.subTest(
                        module=module.__name__,
                        factory=factory_name,
                    ):
                        wrapped = getattr(module, factory_name)
                        self.assertIsNot(
                            wrapped,
                            originals[(module, factory_name)],
                        )
                        self.assertTrue(hasattr(wrapped, "__wrapped__"))

        for key, original in originals.items():
            module, factory_name = key
            self.assertIs(getattr(module, factory_name), original)

    def test_sync_cursor_methods_emit_spans(self):
        method_cases = [
            ("execute", "SELECT id FROM users", (), "SELECT"),
            (
                "executemany",
                "INSERT INTO t VALUES (:1)",
                ([(1,), (2,)],),
                "INSERT",
            ),
            ("callproc", "my_proc", ([1, 2],), "my_proc"),
        ]
        for module in (oracledb, oracledb_connection_module):
            for method, statement, extra_args, span_name in method_cases:
                with self.subTest(module=module.__name__, method=method):
                    self.memory_exporter.clear()
                    connection = _make_mock_connection()
                    expected_result = getattr(
                        connection.cursor.return_value,
                        method,
                    ).return_value
                    with (
                        patch.object(
                            module,
                            "connect",
                            return_value=connection,
                        ),
                        self._instrumented(),
                    ):
                        result = self._run_cursor_method(
                            module,
                            method,
                            statement,
                            *extra_args,
                        )

                    self.assertIs(result, expected_result)
                    spans = self.memory_exporter.get_finished_spans()
                    self.assertEqual(len(spans), 1)
                    span = spans[0]
                    self.assertEqual(span.name, span_name)
                    self.assertIs(span.kind, trace_api.SpanKind.CLIENT)
                    self.assertEqual(
                        span.attributes[DB_SYSTEM],
                        _DATABASE_SYSTEM,
                    )
                    self.assertIsInstance(span.attributes[DB_SYSTEM], str)
                    self.assertEqual(
                        span.attributes[DB_STATEMENT],
                        statement,
                    )
                    self.assertIsInstance(span.attributes[DB_STATEMENT], str)

    def test_connection_attributes_use_oracle_semconv(self):
        connection = _make_mock_connection(
            db_name="FREE",
            db_domain="prod.example.com",
            instance_name="FREE1",
            service_name="FREEPDB1",
            username="app_user",
        )
        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(),
        ):
            self._run_cursor_method()

        span = self.memory_exporter.get_finished_spans()[0]
        expected_attributes = {
            DB_SYSTEM: _DATABASE_SYSTEM,
            DB_NAME: "FREE",
            DB_USER: "app_user",
            ORACLE_DB_NAME: "FREE",
            ORACLE_DB_DOMAIN: "prod.example.com",
            ORACLE_DB_INSTANCE_NAME: "FREE1",
            ORACLE_DB_SERVICE: "FREEPDB1",
        }
        for attribute_name, expected_value in expected_attributes.items():
            with self.subTest(attribute=attribute_name):
                self.assertEqual(
                    span.attributes[attribute_name],
                    expected_value,
                )
                self.assertIsInstance(span.attributes[attribute_name], str)
        self.assertNotIn(NET_PEER_NAME, span.attributes)

    def test_sync_errors_are_recorded_and_reraised_unmodified(self):
        for method in ("execute", "executemany", "callproc"):
            with self.subTest(method=method):
                self.memory_exporter.clear()
                connection = _make_mock_connection()
                error = oracledb.DatabaseError("database error")
                getattr(connection.cursor.return_value, method).side_effect = error
                extra_args = ([(1,)],) if method == "executemany" else ()
                with (
                    patch.object(
                        oracledb,
                        "connect",
                        return_value=connection,
                    ),
                    self._instrumented(),
                    self.assertRaises(oracledb.DatabaseError) as raised,
                ):
                    self._run_cursor_method(
                        oracledb,
                        method,
                        "SELECT 1 FROM dual",
                        *extra_args,
                    )

                self.assertIs(raised.exception, error)
                span = self.memory_exporter.get_finished_spans()[0]
                self.assertIs(
                    span.status.status_code,
                    trace_api.StatusCode.ERROR,
                )
                self.assertTrue(any(event.name == "exception" for event in span.events))

    def test_custom_tracer_provider_is_respected(self):
        other_exporter = InMemorySpanExporter()
        other_provider = TracerProvider()
        other_provider.add_span_processor(SimpleSpanProcessor(other_exporter))
        with (
            patch.object(
                oracledb,
                "connect",
                return_value=_make_mock_connection(),
            ),
            self._instrumented(tracer_provider=other_provider),
        ):
            self._run_cursor_method()

        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
        self.assertEqual(len(other_exporter.get_finished_spans()), 1)

    def test_instrument_connection_and_uninstrument_connection(self):
        instrumentor = OracleDBInstrumentor()
        raw_connection = _make_mock_connection()
        connection = instrumentor.instrument_connection(
            raw_connection,
            tracer_provider=self.tracer_provider,
        )
        self.assertIsInstance(connection, TracedConnectionProxy)

        connection.cursor().execute("SELECT 1 FROM dual")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

        uninstrumented = instrumentor.uninstrument_connection(connection)
        self.assertIs(uninstrumented, raw_connection)
        self.memory_exporter.clear()
        uninstrumented.cursor().execute("SELECT 1 FROM dual")
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())

    @patch("opentelemetry.instrumentation.oracledb.dbapi.wrap_connect")
    def test_instrument_forwards_configuration(self, wrap_connect):
        with self._instrumented(
            enable_commenter=True,
            commenter_options={"db_driver": False},
            enable_attribute_commenter=True,
        ):
            self.assertEqual(wrap_connect.call_count, 2)
            for call in wrap_connect.call_args_list:
                args, kwargs = call
                self.assertEqual(
                    args[0],
                    "opentelemetry.instrumentation.oracledb",
                )
                self.assertEqual(args[2], "connect")
                self.assertEqual(args[3], _DATABASE_SYSTEM)
                self.assertEqual(args[4], _CONNECTION_ATTRIBUTES)
                self.assertEqual(kwargs["version"], __version__)
                self.assertIs(
                    kwargs["db_api_integration_factory"],
                    _OracleDatabaseApiIntegration,
                )
                self.assertTrue(kwargs["enable_commenter"])
                self.assertEqual(
                    kwargs["commenter_options"],
                    {"db_driver": False},
                )
                self.assertTrue(kwargs["enable_attribute_commenter"])


class TestOracleDBInstrumentorAsync(
    _OracleDBTestBase,
    IsolatedAsyncioTestCase,
):
    async def test_async_cursor_methods_emit_spans(self):
        method_cases = [
            ("execute", "SELECT id FROM users", (), "SELECT"),
            (
                "executemany",
                "INSERT INTO t VALUES (:1)",
                ([(1,), (2,)],),
                "INSERT",
            ),
            ("callproc", "my_proc", ([1, 2],), "my_proc"),
        ]
        for module in (oracledb, oracledb_connection_module):
            for method, statement, extra_args, span_name in method_cases:
                with self.subTest(module=module.__name__, method=method):
                    self.memory_exporter.clear()
                    connection = _make_mock_async_connection()
                    expected_result = getattr(
                        connection.cursor.return_value,
                        method,
                    ).return_value
                    with (
                        patch.object(
                            module,
                            "connect_async",
                            MagicMock(return_value=connection),
                        ),
                        self._instrumented(),
                    ):
                        instrumented = await module.connect_async(
                            user="scott",
                            password="tiger",
                            dsn="localhost/freepdb1",
                        )
                        result = await getattr(
                            instrumented.cursor(),
                            method,
                        )(statement, *extra_args)

                    self.assertIs(result, expected_result)
                    span = self.memory_exporter.get_finished_spans()[0]
                    self.assertEqual(span.name, span_name)
                    self.assertIs(span.kind, trace_api.SpanKind.CLIENT)
                    self.assertEqual(
                        span.attributes[DB_SYSTEM],
                        _DATABASE_SYSTEM,
                    )
                    self.assertIsInstance(span.attributes[DB_SYSTEM], str)
                    self.assertEqual(
                        span.attributes[DB_STATEMENT],
                        statement,
                    )
                    self.assertIsInstance(span.attributes[DB_STATEMENT], str)

    async def test_async_connection_attributes_use_oracle_semconv(self):
        connection = _make_mock_async_connection(
            db_name="FREE",
            db_domain="prod.example.com",
            instance_name="FREE1",
            service_name="FREEPDB1",
            username="app_user",
        )
        with (
            patch.object(
                oracledb,
                "connect_async",
                MagicMock(return_value=connection),
            ),
            self._instrumented(),
        ):
            instrumented = await oracledb.connect_async(
                user="app_user",
                password="password",
                dsn="localhost/freepdb1",
            )
            await instrumented.cursor().execute("SELECT 1 FROM dual")

        span = self.memory_exporter.get_finished_spans()[0]
        expected_attributes = {
            DB_SYSTEM: _DATABASE_SYSTEM,
            DB_NAME: "FREE",
            DB_USER: "app_user",
            ORACLE_DB_NAME: "FREE",
            ORACLE_DB_DOMAIN: "prod.example.com",
            ORACLE_DB_INSTANCE_NAME: "FREE1",
            ORACLE_DB_SERVICE: "FREEPDB1",
        }
        for attribute_name, expected_value in expected_attributes.items():
            with self.subTest(attribute=attribute_name):
                self.assertEqual(
                    span.attributes[attribute_name],
                    expected_value,
                )
                self.assertIsInstance(span.attributes[attribute_name], str)
        self.assertNotIn(NET_PEER_NAME, span.attributes)

    async def test_async_errors_are_recorded_and_reraised_unmodified(self):
        for method in ("execute", "executemany", "callproc"):
            with self.subTest(method=method):
                self.memory_exporter.clear()
                connection = _make_mock_async_connection()
                error = oracledb.DatabaseError("database error")
                getattr(connection.cursor.return_value, method).side_effect = error
                extra_args = ([(1,)],) if method == "executemany" else ()
                with (
                    patch.object(
                        oracledb,
                        "connect_async",
                        MagicMock(return_value=connection),
                    ),
                    self._instrumented(),
                ):
                    instrumented = await oracledb.connect_async(
                        user="scott",
                        password="tiger",
                        dsn="localhost/freepdb1",
                    )
                    with self.assertRaises(oracledb.DatabaseError) as raised:
                        await getattr(instrumented.cursor(), method)(
                            "SELECT 1 FROM dual",
                            *extra_args,
                        )

                self.assertIs(raised.exception, error)
                span = self.memory_exporter.get_finished_spans()[0]
                self.assertIs(
                    span.status.status_code,
                    trace_api.StatusCode.ERROR,
                )
                self.assertTrue(any(event.name == "exception" for event in span.events))

    async def test_async_context_manager_exit_result_is_preserved(self):
        connection = _make_mock_async_connection()
        connection.__aexit__.return_value = True
        connection.cursor.return_value.__aexit__.return_value = True
        with (
            patch.object(
                oracledb,
                "connect_async",
                MagicMock(return_value=connection),
            ),
            self._instrumented(),
        ):
            instrumented = await oracledb.connect_async(
                user="scott",
                password="tiger",
                dsn="localhost/freepdb1",
            )
            self.assertTrue(await instrumented.__aexit__(None, None, None))
            self.assertTrue(await instrumented.cursor().__aexit__(None, None, None))

    async def test_connect_async_supports_direct_async_context_manager(self):
        connection = _make_mock_async_connection()
        with (
            patch.object(
                oracledb,
                "connect_async",
                MagicMock(return_value=connection),
            ),
            self._instrumented(),
        ):
            async with oracledb.connect_async(
                user="scott",
                password="tiger",
                dsn="localhost/freepdb1",
            ) as instrumented:
                await instrumented.cursor().execute("SELECT 1 FROM dual")

        connection.__aenter__.assert_awaited_once_with()
        connection.__aexit__.assert_awaited_once_with(None, None, None)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    async def test_cursor_from_async_connection_supports_sync_context_manager(
        self,
    ):
        connection = _make_mock_async_connection()
        with (
            patch.object(
                oracledb,
                "connect_async",
                MagicMock(return_value=connection),
            ),
            self._instrumented(),
        ):
            async with oracledb.connect_async(
                user="scott",
                password="tiger",
                dsn="localhost/freepdb1",
            ) as instrumented:
                with instrumented.cursor():
                    pass

        connection.cursor.return_value.__enter__.assert_called_once_with()
        connection.cursor.return_value.__exit__.assert_called_once_with(None, None, None)
