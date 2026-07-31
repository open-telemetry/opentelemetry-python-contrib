# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os

import pytest
from sqlalchemy.exc import ProgrammingError

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_USER,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)

from .mixins import SQLAlchemyTestMixin

MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": int(os.getenv("TEST_MYSQL_PORT", "3306")),
    "user": os.getenv("TEST_MYSQL_USER", "testuser"),
    "password": os.getenv("TEST_MYSQL_PASSWORD", "testpassword"),
    "database": os.getenv("TEST_MYSQL_DATABASE", "opentelemetry-tests"),
}


class MysqlConnectorTestCase(SQLAlchemyTestMixin):
    """TestCase for mysql-connector engine"""

    __test__ = True

    VENDOR = "mysql"
    SQL_DB = "opentelemetry-tests"
    ENGINE_ARGS = {
        "url": "mysql+mysqlconnector://%(user)s:%(password)s@%(host)s:%(port)s/%(database)s"
        % MYSQL_CONFIG
    }

    def check_meta(self, span):
        # check database connection tags
        self.assertEqual(
            span.attributes.get(NET_PEER_NAME),
            MYSQL_CONFIG["host"],
        )
        self.assertEqual(
            span.attributes.get(NET_PEER_PORT),
            MYSQL_CONFIG["port"],
        )
        self.assertEqual(
            span.attributes.get(DB_NAME),
            MYSQL_CONFIG["database"],
        )
        self.assertEqual(span.attributes.get(DB_USER), MYSQL_CONFIG["user"])

    def test_engine_execute_errors(self):
        # ensures that SQL errors are reported
        with pytest.raises(ProgrammingError):
            with self.connection() as conn:
                conn.execute("SELECT * FROM a_wrong_table").fetchall()

        spans = self.memory_exporter.get_finished_spans()
        # one span for the connection and one for the query
        self.assertEqual(len(spans), 2)
        self.check_meta(spans[0])
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
