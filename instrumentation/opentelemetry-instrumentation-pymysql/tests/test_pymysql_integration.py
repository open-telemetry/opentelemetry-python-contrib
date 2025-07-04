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

from unittest import mock

import pymysql

import opentelemetry.instrumentation.pymysql
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase


class TestPyMysqlIntegration(TestBase):
    # pylint: disable=invalid-name
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            PyMySQLInstrumentor().uninstrument()

    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_instrumentor(self, mock_connect):
        PyMySQLInstrumentor().instrument()

        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.pymysql
        )

        # check that no spans are generated after uninstrument
        PyMySQLInstrumentor().uninstrument()

        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self, mock_connect):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        PyMySQLInstrumentor().instrument(tracer_provider=tracer_provider)

        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(span.resource, resource)

    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_no_op_tracer_provider(self, mock_connect):
        PyMySQLInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )
        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_instrument_connection(self, mock_connect):
        cnx = pymysql.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = PyMySQLInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("opentelemetry.instrumentation.dbapi.instrument_connection")
    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_instrument_connection_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_instrument_connection,
    ):
        cnx = pymysql.connect(database="test")
        cnx = PyMySQLInstrumentor().instrument_connection(
            cnx,
            enable_commenter=True,
            commenter_options={"foo": True},
            enable_attribute_commenter=True,
        )
        cursor = cnx.cursor()
        cursor.execute("SELECT * FROM test")
        kwargs = mock_instrument_connection.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)
        self.assertEqual(kwargs["commenter_options"], {"foo": True})
        self.assertEqual(kwargs["enable_attribute_commenter"], True)

    def test_instrument_connection_with_dbapi_sqlcomment_enabled(self):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            cnx_proxy = PyMySQLInstrumentor().instrument_connection(
                mock_connection,
                enable_commenter=True,
            )
            cnx_proxy.cursor().execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_enabled_stmt_enabled(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            cnx_proxy = PyMySQLInstrumentor().instrument_connection(
                mock_connection,
                enable_commenter=True,
                enable_attribute_commenter=True,
            )
            cnx_proxy.cursor().execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_enabled_with_options(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            cnx_proxy = PyMySQLInstrumentor().instrument_connection(
                mock_connection,
                enable_commenter=True,
                commenter_options={
                    "dbapi_level": False,
                    "dbapi_threadsafety": True,
                    "driver_paramstyle": False,
                },
            )
            cnx_proxy.cursor().execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_threadsafety='123',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            cnx_proxy = PyMySQLInstrumentor().instrument_connection(
                mock_connection,
            )
            cnx_proxy.cursor().execute("Select 1;")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                "Select 1;",
            )
            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "Select 1;",
            )

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_instrument_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_wrap_connect,
    ):
        PyMySQLInstrumentor()._instrument(
            enable_commenter=True,
            commenter_options={"foo": True},
            enable_attribute_commenter=True,
        )
        kwargs = mock_wrap_connect.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)
        self.assertEqual(kwargs["commenter_options"], {"foo": True})
        self.assertEqual(kwargs["enable_attribute_commenter"], True)

    def test_instrument_with_dbapi_sqlcomment_enabled(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            PyMySQLInstrumentor()._instrument(
                enable_commenter=True,
            )
            cnx = mock_connect_module.connect(database="test")
            cursor = cnx.cursor()
            cursor.execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_with_dbapi_sqlcomment_enabled_stmt_enabled(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            PyMySQLInstrumentor()._instrument(
                enable_commenter=True,
                enable_attribute_commenter=True,
            )
            cnx = mock_connect_module.connect(database="test")
            cursor = cnx.cursor()
            cursor.execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )

    def test_instrument_with_dbapi_sqlcomment_enabled_with_options(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            PyMySQLInstrumentor()._instrument(
                enable_commenter=True,
                commenter_options={
                    "dbapi_level": False,
                    "dbapi_threadsafety": True,
                    "driver_paramstyle": False,
                },
            )
            cnx = mock_connect_module.connect(database="test")
            cursor = cnx.cursor()
            cursor.execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='pymysql%%3Afoobar',dbapi_threadsafety='123',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="pymysql",
            __version__="foobar",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with mock.patch(
            "opentelemetry.instrumentation.pymysql.pymysql",
            mock_connect_module,
        ):
            PyMySQLInstrumentor()._instrument()
            cnx = mock_connect_module.connect(database="test")
            cursor = cnx.cursor()
            cursor.execute("Select 1;")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                "Select 1;",
            )
            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "Select 1;",
            )

    @mock.patch("pymysql.connect")
    # pylint: disable=unused-argument
    def test_uninstrument_connection(self, mock_connect):
        PyMySQLInstrumentor().instrument()
        cnx = pymysql.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = PyMySQLInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
