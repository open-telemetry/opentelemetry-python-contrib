# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
from unittest import mock
from unittest.mock import Mock, patch

import pymssql  # type: ignore

import opentelemetry.instrumentation.pymssql
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.test.test_base import TestBase
from opentelemetry.util._importlib_metadata import entry_points


def mock_connect(*args, **kwargs):
    class MockConnection:
        def cursor(self):
            # pylint: disable=no-self-use
            return Mock()

    return MockConnection()


@contextlib.contextmanager
def use_semconv_opt_in(sem_conv_mode):
    env_patch = mock.patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode},
    )
    _OpenTelemetrySemanticConventionStability._initialized = False
    env_patch.start()
    try:
        yield
    finally:
        env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False


class TestPyMSSQLIntegration(TestBase):
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            PyMSSQLInstrumentor().uninstrument()

    def _execute_query_and_get_span(self, cnx):
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.pymssql
        )
        return span

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrumentor(self):
        PyMSSQLInstrumentor().instrument()

        cnx = pymssql.connect(  # pylint: disable=no-member
            host="dbserver.local:1433",
            database="testdb",
            user="dbuser",
            password="dbpassw0rd",
            charset="UTF-8",
            tds_version="7.1",
        )
        span = self._execute_query_and_get_span(cnx)

        self.assertEqual(span.attributes["db.system"], "mssql")
        self.assertEqual(span.attributes["db.name"], "testdb")
        self.assertEqual(span.attributes["db.statement"], "SELECT * FROM test")
        self.assertEqual(span.attributes["db.user"], "dbuser")
        self.assertEqual(span.attributes["net.peer.name"], "dbserver.local")
        self.assertEqual(span.attributes["net.peer.port"], 1433)
        self.assertEqual(span.attributes["db.charset"], "UTF-8")
        self.assertEqual(span.attributes["db.protocol.tds.version"], "7.1")

        # check that no spans are generated after uninstrument
        PyMSSQLInstrumentor().uninstrument()

        cnx = pymssql.connect(database="test")  # pylint: disable=no-member
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrumentor_server_param(self):
        PyMSSQLInstrumentor().instrument()

        # `server` can be used instead of `host`
        cnx = pymssql.connect(server="dbserver.local:1433", database="testdb")  # pylint: disable=no-member
        span = self._execute_query_and_get_span(cnx)

        self.assertEqual(span.attributes["net.peer.name"], "dbserver.local")
        self.assertEqual(span.attributes["net.peer.port"], 1433)

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrumentor_port_param(self):
        PyMSSQLInstrumentor().instrument()

        # port can be specified as a parameter
        cnx = pymssql.connect(  # pylint: disable=no-member
            server="dbserver.local", port="1433", database="testdb"
        )
        span = self._execute_query_and_get_span(cnx)

        self.assertEqual(span.attributes["net.peer.name"], "dbserver.local")
        self.assertEqual(span.attributes["net.peer.port"], 1433)

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrumentor_windows_server(self):
        PyMSSQLInstrumentor().instrument()

        # Windows server names can include special characters
        cnx = pymssql.connect(server=r"(local)\SQLEXPRESS", database="testdb")  # pylint: disable=no-member
        span = self._execute_query_and_get_span(cnx)

        self.assertEqual(
            span.attributes["net.peer.name"], r"(local)\SQLEXPRESS"
        )

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        PyMSSQLInstrumentor().instrument(tracer_provider=tracer_provider)

        cnx = pymssql.connect(database="test")  # pylint: disable=no-member
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(span.resource, resource)

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrument_connection(self):
        cnx = pymssql.connect(database="test")  # pylint: disable=no-member
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = PyMSSQLInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @patch("pymssql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_uninstrument_connection(self):
        PyMSSQLInstrumentor().instrument()
        cnx = pymssql.connect(database="test")  # pylint: disable=no-member
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = PyMSSQLInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    def test_load_entry_point(self):
        self.assertIs(
            next(
                iter(
                    entry_points(
                        group="opentelemetry_instrumentor", name="pymssql"
                    )
                )
            ).load(),
            PyMSSQLInstrumentor,
        )

    @patch("pymssql.connect", new=mock_connect)
    def test_semconv_stable(self):
        """database,http opt-in emits only stable attributes."""
        with use_semconv_opt_in("database,http"):
            PyMSSQLInstrumentor().instrument()
            cnx = pymssql.connect(  # pylint: disable=no-member
                server="dbserver.local",
                port="1433",
                database="testdb",
                user="dbuser",
                password="dbpassw0rd",
                tds_version="7.1",
            )
            span = self._execute_query_and_get_span(cnx)

            self.assertEqual(span.attributes["db.system.name"], "mssql")
            self.assertEqual(span.attributes["db.namespace"], "testdb")
            self.assertEqual(
                span.attributes["db.query.text"], "SELECT * FROM test"
            )
            self.assertEqual(
                span.attributes["server.address"], "dbserver.local"
            )
            self.assertEqual(span.attributes["server.port"], 1433)
            self.assertEqual(span.attributes["db.protocol.tds.version"], "7.1")
            self.assertNotIn("db.system", span.attributes)
            self.assertNotIn("db.name", span.attributes)
            self.assertNotIn("db.statement", span.attributes)
            self.assertNotIn("db.user", span.attributes)
            self.assertNotIn("net.peer.name", span.attributes)
            self.assertNotIn("net.peer.port", span.attributes)

    @patch("pymssql.connect", new=mock_connect)
    def test_semconv_dup(self):
        """database/dup,http/dup emits both legacy and stable."""
        with use_semconv_opt_in("database/dup,http/dup"):
            PyMSSQLInstrumentor().instrument()
            cnx = pymssql.connect(  # pylint: disable=no-member
                server="dbserver.local",
                port="1433",
                database="testdb",
                user="dbuser",
                password="dbpassw0rd",
            )
            span = self._execute_query_and_get_span(cnx)

            self.assertEqual(span.attributes["db.system"], "mssql")
            self.assertEqual(span.attributes["db.system.name"], "mssql")
            self.assertEqual(span.attributes["db.name"], "testdb")
            self.assertEqual(span.attributes["db.namespace"], "testdb")
            self.assertEqual(
                span.attributes["db.statement"], "SELECT * FROM test"
            )
            self.assertEqual(
                span.attributes["db.query.text"], "SELECT * FROM test"
            )
            self.assertEqual(span.attributes["db.user"], "dbuser")
            self.assertEqual(
                span.attributes["net.peer.name"], "dbserver.local"
            )
            self.assertEqual(
                span.attributes["server.address"], "dbserver.local"
            )
            self.assertEqual(span.attributes["net.peer.port"], 1433)
            self.assertEqual(span.attributes["server.port"], 1433)
