# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import itertools
import sqlite3
import time
from unittest import mock

import sqlalchemy
from sqlalchemy.pool import QueuePool

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.sqlalchemy.engine import (
    EngineTracer,
    _wrap_create_async_engine,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.metrics.export import Histogram
from opentelemetry.test.test_base import TestBase

SCOPE = "opentelemetry.instrumentation.sqlalchemy"

CONNECTION_COUNT = "db.client.connection.count"
CONNECTIONS_USAGE = "db.client.connections.usage"
CONNECTION_CREATE_TIME = "db.client.connection.create_time"
POOL_NAME = "db.client.connection.pool.name"
STATE = "db.client.connection.state"

# Patched so the tests control the clock that the create_time listeners read
ENGINE_TIME = "opentelemetry.instrumentation.sqlalchemy.engine.time"


def fail_first_connect(dialect, error):
    """Make the dialect's next DBAPI connect raise ``error``, then connect as usual."""
    real_connect = dialect.connect
    calls = []

    def connect(*args, **kwargs):
        calls.append(None)
        if len(calls) == 1:
            raise error
        return real_connect(*args, **kwargs)

    return mock.patch.object(dialect, "connect", side_effect=connect)


class TestSqlalchemyMetricsInstrumentation(TestBase):  # pylint: disable=too-many-public-methods
    def setUp(self):
        super().setUp()
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
        )

    def tearDown(self):
        super().tearDown()
        SQLAlchemyInstrumentor().uninstrument()

    @staticmethod
    def create_instrumented_async_engine():
        # sqlalchemy.ext.asyncio keeps a reference to the instrumented
        # create_engine even after uninstrumenting, so create the engine with
        # instrumentation suppressed and instrument it directly. This gives it
        # a single EngineTracer, which uninstrument() can cleanly remove.
        SQLAlchemyInstrumentor().uninstrument()
        from sqlalchemy.ext.asyncio import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            create_async_engine,
        )

        with suppress_instrumentation():
            engine = create_async_engine(
                "sqlite+aiosqlite:///:memory:",
                pool_logging_name="pool_test_name",
            )
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        return engine

    def get_metric(self, name):
        metrics = [m for m in self.get_sorted_metrics(SCOPE) if m.name == name]
        self.assertLessEqual(len(metrics), 1)
        return metrics[0] if metrics else None

    def assert_pool_idle_used_expected(self, pool_name, idle, used):
        metric = self.get_metric(CONNECTION_COUNT)
        self.assertIsNotNone(metric)
        self.assert_metric_expected(
            metric,
            [
                self.create_number_data_point(
                    value=idle,
                    attributes={POOL_NAME: pool_name, STATE: "idle"},
                ),
                self.create_number_data_point(
                    value=used,
                    attributes={POOL_NAME: pool_name, STATE: "used"},
                ),
            ],
        )

    def test_metrics_one_connection(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        self.assertEqual(len(self.get_sorted_metrics(SCOPE)), 0)

        with engine.connect():
            self.assert_pool_idle_used_expected(pool_name=pool_name, idle=0, used=1)

        # After the connection is closed
        self.assert_pool_idle_used_expected(pool_name=pool_name, idle=1, used=0)

    def test_metrics_without_pool_name(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        self.assertEqual(len(self.get_sorted_metrics(SCOPE)), 0)

        with engine.connect():
            self.assert_pool_idle_used_expected(pool_name=pool_name, idle=0, used=1)

        # After the connection is closed
        self.assert_pool_idle_used_expected(pool_name=pool_name, idle=1, used=0)

    def test_metrics_two_connections(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        self.assertEqual(len(self.get_sorted_metrics(SCOPE)), 0)

        with engine.connect():
            with engine.connect():
                self.assert_pool_idle_used_expected(pool_name, idle=0, used=2)

            # After the first connection is closed
            self.assert_pool_idle_used_expected(pool_name, idle=1, used=1)

        # After the two connections are closed
        self.assert_pool_idle_used_expected(pool_name, idle=2, used=0)

    def test_metrics_connections(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        self.assertEqual(len(self.get_sorted_metrics(SCOPE)), 0)

        with engine.connect():
            with engine.connect():
                self.assert_pool_idle_used_expected(pool_name=pool_name, idle=0, used=2)

            # After the first connection is closed
            self.assert_pool_idle_used_expected(pool_name=pool_name, idle=1, used=1)

            # Resume from idle to used
            with engine.connect():
                self.assert_pool_idle_used_expected(pool_name=pool_name, idle=0, used=2)

        # After the two connections are closed
        self.assert_pool_idle_used_expected(pool_name=pool_name, idle=2, used=0)

    def test_metrics_checkout_suppressed_checkin_not_suppressed(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            pool_size=5,
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        with engine.connect():
            pass

        for _ in range(3):
            with suppress_instrumentation():
                conn = engine.connect()
            conn.close()

        self.assert_pool_idle_used_expected(pool_name=pool_name, idle=1, used=0)

    def test_metric_uninstrument(self):
        SQLAlchemyInstrumentor().uninstrument()
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
        )

        engine.connect()

        self.assertEqual(len(self.get_sorted_metrics(SCOPE)), 0)

    def test_deprecated_usage_metric_not_emitted(self):
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )

        with engine.connect():
            metric_names = {m.name for m in self.get_sorted_metrics(SCOPE)}

        self.assertIn(CONNECTION_COUNT, metric_names)
        self.assertNotIn(CONNECTIONS_USAGE, metric_names)

    def test_create_time_recorded_on_new_connection(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        self.assertIsNone(self.get_metric(CONNECTION_CREATE_TIME))

        with engine.connect():
            pass
        # Reusing the pooled connection does not create a new one
        with engine.connect():
            pass

        metric = self.get_metric(CONNECTION_CREATE_TIME)
        self.assertIsNotNone(metric)
        self.assertEqual(metric.unit, "s")
        self.assertIsInstance(metric.data, Histogram)
        data_points = list(metric.data.data_points)
        self.assertEqual(len(data_points), 1)
        point = data_points[0]
        self.assertEqual(dict(point.attributes), {POOL_NAME: pool_name})
        self.assertIsInstance(point.attributes[POOL_NAME], str)
        self.assertEqual(point.count, 1)
        self.assertIsInstance(point.sum, float)
        self.assertGreaterEqual(point.sum, 0)

    def test_create_time_recorded_per_new_connection(self):
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )

        with engine.connect():
            with engine.connect():
                pass

        metric = self.get_metric(CONNECTION_CREATE_TIME)
        data_points = list(metric.data.data_points)
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0].count, 2)

    def test_create_time_recorded_for_async_engine(self):
        async def run():
            engine = self.create_instrumented_async_engine()
            async with engine.connect():
                pass
            await engine.dispose()

        asyncio.run(run())

        metric = self.get_metric(CONNECTION_CREATE_TIME)
        self.assertIsNotNone(metric)
        data_points = list(metric.data.data_points)
        self.assertEqual(data_points[0].count, 1)
        self.assertEqual(dict(data_points[0].attributes), {POOL_NAME: "pool_test_name"})

    def test_create_time_excludes_other_connect_listeners(self):
        SQLAlchemyInstrumentor().uninstrument()
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )
        slow_listener_seconds = 0.2

        def slow_connect_listener(_dbapi_connection, _connection_record):
            time.sleep(slow_listener_seconds)

        sqlalchemy.event.listen(engine, "connect", slow_connect_listener)
        SQLAlchemyInstrumentor().instrument(engine=engine)

        with engine.connect():
            pass

        point = list(self.get_metric(CONNECTION_CREATE_TIME).data.data_points)[0]
        self.assertEqual(point.count, 1)
        self.assertLess(point.sum, slow_listener_seconds)

    def test_create_time_recorded_when_suppressed(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        with suppress_instrumentation():
            with engine.connect():
                pass

        point = list(self.get_metric(CONNECTION_CREATE_TIME).data.data_points)[0]
        self.assertEqual(point.count, 1)
        self.assertEqual(dict(point.attributes), {POOL_NAME: pool_name})

    def test_create_time_not_recorded_with_custom_creator(self):
        # A custom creator bypasses the do_connect event, so there is no
        # start time to measure from.
        engine = sqlalchemy.create_engine(
            "sqlite://",
            creator=lambda: sqlite3.connect(":memory:"),
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )

        with engine.connect():
            pass

        self.assertIsNone(self.get_metric(CONNECTION_CREATE_TIME))

    def test_create_time_records_exact_duration(self):
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )

        # The clock is read once before and once after each DBAPI connect
        with mock.patch(ENGINE_TIME) as mock_time:
            mock_time.perf_counter.side_effect = [100.0, 102.5, 200.0, 201.0]
            with engine.connect():
                with engine.connect():
                    pass

        point = list(self.get_metric(CONNECTION_CREATE_TIME).data.data_points)[0]
        self.assertEqual(point.count, 2)
        self.assertEqual(point.sum, 3.5)
        self.assertEqual(point.min, 1.0)
        self.assertEqual(point.max, 2.5)

    def test_create_time_not_recorded_for_failed_connect(self):
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )
        error = engine.dialect.dbapi.OperationalError("connect failed")

        with mock.patch(ENGINE_TIME) as mock_time, fail_first_connect(engine.dialect, error):
            # The failed connect reads the clock once and never finishes
            mock_time.perf_counter.side_effect = [100.0, 200.0, 201.0]
            with self.assertRaises(sqlalchemy.exc.OperationalError) as caught:
                engine.connect()
            self.assertIs(caught.exception.orig, error)
            self.assertIsNone(self.get_metric(CONNECTION_CREATE_TIME))

            with engine.connect():
                pass

        # Only the successful connect is recorded, with its own duration
        point = list(self.get_metric(CONNECTION_CREATE_TIME).data.data_points)[0]
        self.assertEqual(point.count, 1)
        self.assertEqual(point.sum, 1.0)

    def test_create_time_not_recorded_for_failed_async_connect(self):
        async def run():
            engine = self.create_instrumented_async_engine()
            dialect = engine.sync_engine.dialect
            error = dialect.dbapi.OperationalError("connect failed")

            with mock.patch(ENGINE_TIME) as mock_time, fail_first_connect(dialect, error):
                # Each clock reading is one second after the last, so the
                # successful connect measures exactly one second
                mock_time.perf_counter.side_effect = itertools.count(100.0)
                with self.assertRaises(sqlalchemy.exc.OperationalError) as caught:
                    async with engine.connect():
                        pass
                self.assertIs(caught.exception.orig, error)
                self.assertIsNone(self.get_metric(CONNECTION_CREATE_TIME))

                async with engine.connect():
                    pass
            await engine.dispose()

        asyncio.run(run())

        point = list(self.get_metric(CONNECTION_CREATE_TIME).data.data_points)[0]
        self.assertEqual(point.count, 1)
        self.assertEqual(point.sum, 1.0)

    def test_create_time_listeners_not_registered_without_histogram(self):
        SQLAlchemyInstrumentor().uninstrument()
        engine = sqlalchemy.create_engine("sqlite:///:memory:", poolclass=QueuePool)
        tracer = EngineTracer(mock.Mock(), engine, mock.Mock())

        self.assertFalse(sqlalchemy.event.contains(engine, "do_connect", tracer._dialect_do_connect))
        self.assertFalse(sqlalchemy.event.contains(engine, "connect", tracer._record_connection_create_time))

    def test_create_async_engine_wrapper_passes_create_time(self):
        histogram = mock.Mock()
        engine = mock.Mock()
        wrapper = _wrap_create_async_engine(mock.Mock(), mock.Mock(), connection_create_time=histogram)

        with mock.patch("opentelemetry.instrumentation.sqlalchemy.engine.EngineTracer") as tracer_cls:
            self.assertIs(wrapper(lambda: engine, None, (), {}), engine)

        tracer_cls.assert_called_once()
        self.assertIs(tracer_cls.call_args.args[1], engine.sync_engine)
        self.assertIs(tracer_cls.call_args.kwargs["connection_create_time"], histogram)
