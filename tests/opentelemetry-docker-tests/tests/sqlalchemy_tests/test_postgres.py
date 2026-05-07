# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os

import psycopg2
import pytest
from sqlalchemy.exc import ProgrammingError

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)

from .mixins import SQLAlchemyTestMixin

SCOPE = "opentelemetry.instrumentation.sqlalchemy"

POSTGRES_CONFIG = {
    "host": "127.0.0.1",
    "port": int(os.getenv("TEST_POSTGRES_PORT", "5432")),
    "user": os.getenv("TEST_POSTGRES_USER", "testuser"),
    "password": os.getenv("TEST_POSTGRES_PASSWORD", "testpassword"),
    "dbname": os.getenv("TEST_POSTGRES_DB", "opentelemetry-tests"),
}


class PostgresTestCase(SQLAlchemyTestMixin):
    """TestCase for Postgres Engine"""

    __test__ = True

    VENDOR = "postgresql"
    SQL_DB = "opentelemetry-tests"
    ENGINE_ARGS = {
        "url": "postgresql://%(user)s:%(password)s@%(host)s:%(port)s/%(dbname)s"
        % POSTGRES_CONFIG
    }

    def check_meta(self, span):
        # check database connection tags
        self.assertEqual(
            span.attributes.get(NET_PEER_NAME),
            POSTGRES_CONFIG["host"],
        )
        self.assertEqual(
            span.attributes.get(NET_PEER_PORT),
            POSTGRES_CONFIG["port"],
        )

    def test_engine_execute_errors(self):
        # ensures that SQL errors are reported
        with pytest.raises(ProgrammingError):
            with self.connection() as conn:
                conn.execute("SELECT * FROM a_wrong_table").fetchall()

        spans = self.memory_exporter.get_finished_spans()
        # one span for the connection and one for the query
        self.assertEqual(len(spans), 2)
        span = spans[1]
        # span fields
        self.assertEqual(span.name, "SELECT opentelemetry-tests")
        self.assertEqual(
            span.attributes.get(DB_STATEMENT),
            "SELECT * FROM a_wrong_table",
        )
        self.assertEqual(span.attributes.get(DB_NAME), self.SQL_DB)
        self.check_meta(span)
        self.assertTrue(span.end_time - span.start_time > 0)
        # check the error
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )
        self.assertIn("a_wrong_table", span.status.description)


class PostgresCreatorTestCase(PostgresTestCase):
    """TestCase for Postgres Engine that includes the same tests set
    of `PostgresTestCase`, but it uses a specific `creator` function.
    """

    VENDOR = "postgresql"
    SQL_DB = "opentelemetry-tests"
    ENGINE_ARGS = {
        "url": "postgresql://",
        "creator": lambda: psycopg2.connect(**POSTGRES_CONFIG),
    }


class PostgresMetricsTestCase(PostgresTestCase):
    __test__ = True

    VENDOR = "postgresql"
    SQL_DB = "opentelemetry-tests"
    ENGINE_ARGS = {
        "url": "postgresql://%(user)s:%(password)s@%(host)s:%(port)s/%(dbname)s"
        % POSTGRES_CONFIG
    }

    def test_metrics_pool_name(self):
        with self.connection() as conn:
            conn.execute("SELECT 1 + 1").fetchall()

        pool_name = "{}://{}:{}/{}".format(
            self.VENDOR,
            POSTGRES_CONFIG["host"],
            POSTGRES_CONFIG["port"],
            self.SQL_DB,
        )
        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(len(metrics), 1)
        self.assert_metric_expected(
            metrics[0],
            [
                self.create_number_data_point(
                    value=0,
                    attributes={"pool.name": pool_name, "state": "idle"},
                ),
                self.create_number_data_point(
                    value=0,
                    attributes={"pool.name": pool_name, "state": "used"},
                ),
            ],
        )
