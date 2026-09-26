# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import sqlalchemy
from sqlalchemy.pool import QueuePool

from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.test.test_base import TestBase

SCOPE = "opentelemetry.instrumentation.sqlalchemy"

CONNECTION_COUNT = "db.client.connection.count"
CONNECTIONS_USAGE = "db.client.connections.usage"
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

    def assert_pool_idle_used_expected(self, pool_name, idle, used):
        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].name, CONNECTION_COUNT)
        self.assert_metric_expected(
            metrics[0],
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
