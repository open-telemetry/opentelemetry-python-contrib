# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import sqlalchemy
from sqlalchemy.pool import QueuePool

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.metrics.export import Histogram
from opentelemetry.test.test_base import TestBase

SCOPE = "opentelemetry.instrumentation.sqlalchemy"

CONNECTION_COUNT = "db.client.connection.count"
CONNECTIONS_USAGE = "db.client.connections.usage"
CONNECTION_USE_TIME = "db.client.connection.use_time"
POOL_NAME = "db.client.connection.pool.name"
STATE = "db.client.connection.state"


class TestSqlalchemyMetricsInstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
        )

    def tearDown(self):
        super().tearDown()
        SQLAlchemyInstrumentor().uninstrument()

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

    def test_use_time_recorded_on_checkin(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        with engine.connect():
            # Nothing is recorded while the connection is still checked out
            self.assertIsNone(self.get_metric(CONNECTION_USE_TIME))

        metric = self.get_metric(CONNECTION_USE_TIME)
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

    def test_use_time_recorded_per_checkout(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        with engine.connect():
            with engine.connect():
                pass
        with engine.connect():
            pass

        metric = self.get_metric(CONNECTION_USE_TIME)
        data_points = list(metric.data.data_points)
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0].count, 3)

    def test_use_time_recorded_for_suppressed_checkout(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        with suppress_instrumentation():
            conn = engine.connect()
        conn.close()

        metric = self.get_metric(CONNECTION_USE_TIME)
        self.assertIsNotNone(metric)
        data_points = list(metric.data.data_points)
        self.assertEqual(data_points[0].count, 1)
        self.assertEqual(dict(data_points[0].attributes), {POOL_NAME: pool_name})

    def test_use_time_recorded_for_suppressed_checkin(self):
        pool_name = "pool_test_name"
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name=pool_name,
        )

        conn = engine.connect()
        with suppress_instrumentation():
            conn.close()

        metric = self.get_metric(CONNECTION_USE_TIME)
        self.assertIsNotNone(metric)
        data_points = list(metric.data.data_points)
        self.assertEqual(data_points[0].count, 1)
        self.assertEqual(dict(data_points[0].attributes), {POOL_NAME: pool_name})

    def test_use_time_records_exact_duration(self):
        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            poolclass=QueuePool,
            pool_logging_name="pool_test_name",
        )

        # The clock is read once on checkout and once on checkin
        with mock.patch("opentelemetry.instrumentation.sqlalchemy.engine.time") as mock_time:
            mock_time.perf_counter.side_effect = [100.0, 102.5, 200.0, 201.0]
            with engine.connect():
                pass
            with engine.connect():
                pass

        point = list(self.get_metric(CONNECTION_USE_TIME).data.data_points)[0]
        self.assertEqual(point.count, 2)
        self.assertEqual(point.sum, 3.5)
        self.assertEqual(point.min, 1.0)
        self.assertEqual(point.max, 2.5)
