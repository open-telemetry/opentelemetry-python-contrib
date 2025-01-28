# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import Mock, patch

import pymssql  # type: ignore

import opentelemetry.instrumentation.pymssql
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
        self.assertEqual(span.attributes["net.peer.port"], "1433")
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
        self.assertEqual(span.attributes["net.peer.port"], "1433")

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
        self.assertEqual(span.attributes["net.peer.port"], "1433")

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
