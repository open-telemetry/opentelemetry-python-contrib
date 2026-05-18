# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import pytest
from sqlalchemy.exc import OperationalError

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
)

from .mixins import SQLAlchemyTestMixin


class SQLiteTestCase(SQLAlchemyTestMixin):
    """TestCase for the SQLite engine"""

    __test__ = True

    VENDOR = "sqlite"
    SQL_DB = ":memory:"
    ENGINE_ARGS = {"url": "sqlite:///:memory:"}

    def test_engine_execute_errors(self):
        # ensures that SQL errors are reported
        stmt = "SELECT * FROM a_wrong_table"
        with pytest.raises(OperationalError):
            with self.connection() as conn:
                conn.execute(stmt).fetchall()

        spans = self.memory_exporter.get_finished_spans()
        # one span for the connection and one span for the query
        self.assertEqual(len(spans), 2)
        span = spans[1]
        # span fields
        self.assertEqual(span.name, "SELECT :memory:")
        self.assertEqual(
            span.attributes.get(DB_STATEMENT),
            "SELECT * FROM a_wrong_table",
        )
        self.assertEqual(span.attributes.get(DB_NAME), self.SQL_DB)
        self.assertTrue((span.end_time - span.start_time) > 0)
        # check the error
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )
        self.assertEqual(
            span.status.description, "no such table: a_wrong_table"
        )
