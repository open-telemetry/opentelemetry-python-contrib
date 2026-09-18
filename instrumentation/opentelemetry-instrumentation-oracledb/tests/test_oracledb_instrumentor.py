# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib
from contextlib import contextmanager
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

import oracledb

try:
    # wrapt 2.0.0+
    from wrapt import BaseObjectProxy  # pylint: disable=no-name-in-module
except ImportError:
    from wrapt import ObjectProxy as BaseObjectProxy

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.dbapi import TracedConnectionProxy
from opentelemetry.instrumentation.oracledb import (
    _CONNECTION_ATTRIBUTES,
    _DATABASE_SYSTEM,
    _DATABASE_SYSTEM_NAME,
    OracleDBInstrumentor,
    _OracleDatabaseApiIntegration,
)
from opentelemetry.instrumentation.oracledb.package import _instruments
from opentelemetry.instrumentation.oracledb.version import __version__
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.oracle_attributes import (
    ORACLE_DB_DOMAIN,
    ORACLE_DB_INSTANCE_NAME,
    ORACLE_DB_NAME,
    ORACLE_DB_SERVICE,
)
from opentelemetry.semconv._incubating.metrics.db_metrics import (
    DB_CLIENT_OPERATION_DURATION,
    DB_CLIENT_RESPONSE_RETURNED_ROWS,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_OPERATION_NAME,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)

oracledb_connection_module = importlib.import_module("oracledb.connection")


def _make_mock_connection(
    *,
    db_name: str = "orcl",
    db_unique_name: str | None = None,
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
    connection.db_unique_name = db_unique_name
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
    db_unique_name: str | None = None,
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
    connection.db_unique_name = db_unique_name
    connection.db_domain = db_domain
    connection.instance_name = instance_name
    connection.service_name = service_name
    connection.username = username
    connection.cursor.return_value = cursor
    connection.__aenter__ = AsyncMock(return_value=connection)
    connection.__aexit__ = AsyncMock(return_value=None)
    return connection


def _assert_db_metrics(
    metrics_reader: InMemoryMetricReader,
    expected_rows: int,
) -> None:
    metrics_data = metrics_reader.get_metrics_data()
    assert metrics_data is not None
    metrics = {
        metric.name: metric
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    assert set(metrics) == {
        DB_CLIENT_OPERATION_DURATION,
        DB_CLIENT_RESPONSE_RETURNED_ROWS,
    }

    for metric in metrics.values():
        points = list(metric.data.data_points)
        assert len(points) == 1
        attributes = dict(points[0].attributes)
        assert set(attributes) == {
            DB_OPERATION_NAME,
            DB_SYSTEM_NAME,
        }
        assert attributes[DB_SYSTEM_NAME] == _DATABASE_SYSTEM_NAME
        assert isinstance(attributes[DB_SYSTEM_NAME], str)
        assert attributes[DB_OPERATION_NAME] == "SELECT"
        assert isinstance(attributes[DB_OPERATION_NAME], str)
        assert points[0].count == 1
        assert isinstance(points[0].count, int)

    rows_point = list(metrics[DB_CLIENT_RESPONSE_RETURNED_ROWS].data.data_points)[0]
    assert rows_point.sum == expected_rows
    assert isinstance(rows_point.sum, int)


class _OracleDBTestBase:  # pylint: disable=invalid-name
    tracer_provider: TracerProvider
    memory_exporter: InMemorySpanExporter

    def setUp(self) -> None:
        _OpenTelemetrySemanticConventionStability._initialized = False  # pylint: disable=protected-access
        self.tracer_provider = TracerProvider()
        self.memory_exporter = InMemorySpanExporter()
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.memory_exporter))

    def tearDown(self) -> None:
        instrumentor = OracleDBInstrumentor()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        self.memory_exporter.clear()
        _OpenTelemetrySemanticConventionStability._initialized = False  # pylint: disable=protected-access

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

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
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
                        span.attributes[DB_SYSTEM_NAME],
                        _DATABASE_SYSTEM_NAME,
                    )
                    self.assertIsInstance(span.attributes[DB_SYSTEM_NAME], str)
                    self.assertEqual(
                        span.attributes[DB_QUERY_TEXT],
                        statement,
                    )
                    self.assertIsInstance(span.attributes[DB_QUERY_TEXT], str)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: ""},
    )
    def test_legacy_database_system(self):
        connection = _make_mock_connection()
        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(),
        ):
            self._run_cursor_method()

        attributes = self.memory_exporter.get_finished_spans()[0].attributes
        self.assertEqual(attributes[DB_SYSTEM], _DATABASE_SYSTEM)
        self.assertIsInstance(attributes[DB_SYSTEM], str)
        self.assertNotIn(DB_SYSTEM_NAME, attributes)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database/dup"},
    )
    def test_duplicate_database_system(self):
        connection = _make_mock_connection()
        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(),
        ):
            self._run_cursor_method()

        attributes = self.memory_exporter.get_finished_spans()[0].attributes
        for attribute in (DB_SYSTEM, DB_SYSTEM_NAME):
            self.assertEqual(attributes[attribute], _DATABASE_SYSTEM_NAME)
            self.assertIsInstance(attributes[attribute], str)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
    def test_connection_attributes_use_oracle_semconv(self):
        connection = _make_mock_connection(
            db_name="FREE",
            db_unique_name="FREE_UNIQUE",
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
            DB_SYSTEM_NAME: _DATABASE_SYSTEM_NAME,
            DB_NAMESPACE: "FREE_UNIQUE",
            DB_QUERY_TEXT: "SELECT 1 FROM dual",
            ORACLE_DB_NAME: "FREE",
            ORACLE_DB_DOMAIN: "prod.example.com",
            ORACLE_DB_INSTANCE_NAME: "FREE1",
            ORACLE_DB_SERVICE: "FREEPDB1",
        }
        self.assertEqual(dict(span.attributes), expected_attributes)
        for attribute_value in span.attributes.values():
            self.assertIsInstance(attribute_value, str)
        for unavailable_attribute in (
            DB_OPERATION_NAME,
            SERVER_ADDRESS,
            SERVER_PORT,
        ):
            self.assertNotIn(unavailable_attribute, span.attributes)

    def test_sync_connection_attribute_writes_are_forwarded(self):
        connection = _make_mock_connection()
        connection.autocommit = False
        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(),
        ):
            instrumented = oracledb.connect(
                user="scott",
                password="tiger",
                dsn="localhost/freepdb1",
            )
            self.assertIsInstance(instrumented, BaseObjectProxy)
            instrumented.autocommit = True

        self.assertTrue(connection.autocommit)

    def test_sync_cursor_attribute_writes_are_forwarded(self):
        connection = _make_mock_connection()
        cursor = connection.cursor.return_value
        cursor.arraysize = 100
        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(),
        ):
            instrumented = oracledb.connect(
                user="scott",
                password="tiger",
                dsn="localhost/freepdb1",
            )
            instrumented_cursor = instrumented.cursor()
            self.assertIsInstance(instrumented_cursor, BaseObjectProxy)
            instrumented_cursor.arraysize = 200

        self.assertEqual(cursor.arraysize, 200)

    def test_sync_pool_releases_instrumented_connection(self):
        connection = MagicMock(spec=oracledb.Connection)
        pool = oracledb.ConnectionPool.__new__(oracledb.ConnectionPool)
        pool._impl = MagicMock()
        pool._impl.return_connection = MagicMock()
        pool.on_connect_callback = None

        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(),
        ):
            pool._set_connection_type(None)
            instrumented = pool.acquire()
            self.assertIsInstance(instrumented, BaseObjectProxy)
            self.assertIsInstance(instrumented, oracledb.Connection)
            pool.release(instrumented)

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

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
    def test_custom_meter_provider_is_respected(self):
        metrics_reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[metrics_reader])
        connection = _make_mock_connection()
        connection.cursor.return_value.rowcount = 3
        with (
            patch.object(oracledb, "connect", return_value=connection),
            self._instrumented(meter_provider=meter_provider),
        ):
            self._run_cursor_method()

        _assert_db_metrics(metrics_reader, 3)

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

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
    def test_instrument_connection_uses_custom_meter_provider(self):
        metrics_reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[metrics_reader])
        raw_connection = _make_mock_connection()
        raw_connection.cursor.return_value.rowcount = 4
        connection = OracleDBInstrumentor.instrument_connection(
            raw_connection,
            tracer_provider=self.tracer_provider,
            meter_provider=meter_provider,
        )

        connection.cursor().execute("SELECT 1 FROM dual")

        _assert_db_metrics(metrics_reader, 4)

    @patch("opentelemetry.instrumentation.oracledb._wrap_connect_async")
    @patch("opentelemetry.instrumentation.oracledb.dbapi.wrap_connect")
    def test_instrument_forwards_configuration(
        self,
        wrap_connect,
        wrap_connect_async,
    ):
        meter_provider = MagicMock()
        with self._instrumented(
            enable_commenter=True,
            commenter_options={"db_driver": False},
            enable_attribute_commenter=True,
            meter_provider=meter_provider,
        ):
            for wrapper, method_name in (
                (wrap_connect, "connect"),
                (wrap_connect_async, "connect_async"),
            ):
                self.assertEqual(wrapper.call_count, 2)
                for call in wrapper.call_args_list:
                    args, kwargs = call
                    self.assertEqual(
                        args[0],
                        "opentelemetry.instrumentation.oracledb",
                    )
                    self.assertEqual(args[2], method_name)
                    self.assertEqual(args[3], _DATABASE_SYSTEM)
                    self.assertEqual(args[4], _CONNECTION_ATTRIBUTES)
                    self.assertEqual(kwargs["version"], __version__)
                    self.assertIs(kwargs["meter_provider"], meter_provider)
                    self.assertTrue(kwargs["enable_commenter"])
                    self.assertEqual(
                        kwargs["commenter_options"],
                        {"db_driver": False},
                    )
                    self.assertTrue(kwargs["enable_attribute_commenter"])

            for call in wrap_connect.call_args_list:
                self.assertIs(
                    call.kwargs["db_api_integration_factory"],
                    _OracleDatabaseApiIntegration,
                )


class TestOracleDBInstrumentorAsync(
    _OracleDBTestBase,
    IsolatedAsyncioTestCase,
):
    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
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
                        span.attributes[DB_SYSTEM_NAME],
                        _DATABASE_SYSTEM_NAME,
                    )
                    self.assertIsInstance(span.attributes[DB_SYSTEM_NAME], str)
                    self.assertEqual(
                        span.attributes[DB_QUERY_TEXT],
                        statement,
                    )
                    self.assertIsInstance(span.attributes[DB_QUERY_TEXT], str)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: ""},
    )
    async def test_async_legacy_database_system(self):
        connection = _make_mock_async_connection()
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
            await instrumented.cursor().execute("SELECT 1 FROM dual")

        attributes = self.memory_exporter.get_finished_spans()[0].attributes
        self.assertEqual(attributes[DB_SYSTEM], _DATABASE_SYSTEM)
        self.assertIsInstance(attributes[DB_SYSTEM], str)
        self.assertNotIn(DB_SYSTEM_NAME, attributes)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database/dup"},
    )
    async def test_async_duplicate_database_system(self):
        connection = _make_mock_async_connection()
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
            await instrumented.cursor().execute("SELECT 1 FROM dual")

        attributes = self.memory_exporter.get_finished_spans()[0].attributes
        for attribute in (DB_SYSTEM, DB_SYSTEM_NAME):
            self.assertEqual(attributes[attribute], _DATABASE_SYSTEM_NAME)
            self.assertIsInstance(attributes[attribute], str)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
    async def test_async_connection_attributes_use_oracle_semconv(self):
        connection = _make_mock_async_connection(
            db_name="FREE",
            db_unique_name="FREE_UNIQUE",
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
            DB_SYSTEM_NAME: _DATABASE_SYSTEM_NAME,
            DB_NAMESPACE: "FREE_UNIQUE",
            DB_QUERY_TEXT: "SELECT 1 FROM dual",
            ORACLE_DB_NAME: "FREE",
            ORACLE_DB_DOMAIN: "prod.example.com",
            ORACLE_DB_INSTANCE_NAME: "FREE1",
            ORACLE_DB_SERVICE: "FREEPDB1",
        }
        self.assertEqual(dict(span.attributes), expected_attributes)
        for attribute_value in span.attributes.values():
            self.assertIsInstance(attribute_value, str)
        for unavailable_attribute in (
            DB_OPERATION_NAME,
            SERVER_ADDRESS,
            SERVER_PORT,
        ):
            self.assertNotIn(unavailable_attribute, span.attributes)

    @patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: "database"},
    )
    async def test_async_custom_meter_provider_is_respected(self):
        metrics_reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[metrics_reader])
        connection = _make_mock_async_connection()
        connection.cursor.return_value.rowcount = 5
        with (
            patch.object(
                oracledb,
                "connect_async",
                MagicMock(return_value=connection),
            ),
            self._instrumented(meter_provider=meter_provider),
        ):
            instrumented = await oracledb.connect_async(
                user="scott",
                password="tiger",
                dsn="localhost/freepdb1",
            )
            await instrumented.cursor().execute("SELECT 1 FROM dual")

        _assert_db_metrics(metrics_reader, 5)

    async def test_async_connection_attribute_writes_are_forwarded(self):
        connection = _make_mock_async_connection()
        connection.autocommit = False
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
            self.assertIsInstance(instrumented, BaseObjectProxy)
            instrumented.autocommit = True

        self.assertTrue(connection.autocommit)

    async def test_async_cursor_attribute_writes_are_forwarded(self):
        connection = _make_mock_async_connection()
        cursor = connection.cursor.return_value
        cursor.arraysize = 100
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
            instrumented_cursor = instrumented.cursor()
            self.assertIsInstance(instrumented_cursor, BaseObjectProxy)
            instrumented_cursor.arraysize = 200

        self.assertEqual(cursor.arraysize, 200)

    async def test_async_pool_releases_instrumented_connection(self):
        connection = MagicMock(spec=oracledb.AsyncConnection)
        pool = oracledb.AsyncConnectionPool.__new__(oracledb.AsyncConnectionPool)
        pool._impl = MagicMock()
        pool._impl.return_connection = AsyncMock()
        pool.on_connect_callback = None

        with (
            patch.object(
                oracledb,
                "connect_async",
                AsyncMock(return_value=connection),
            ),
            self._instrumented(),
        ):
            pool._set_connection_type(None)
            instrumented = await pool.acquire()
            self.assertIsInstance(instrumented, BaseObjectProxy)
            self.assertIsInstance(instrumented, oracledb.AsyncConnection)
            await pool.release(instrumented)

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
