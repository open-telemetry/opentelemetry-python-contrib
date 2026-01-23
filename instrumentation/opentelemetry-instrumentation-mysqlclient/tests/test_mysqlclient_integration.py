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

import MySQLdb

import opentelemetry.instrumentation.mysqlclient
from opentelemetry.instrumentation.mysqlclient import MySQLClientInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_STATEMENT,
)
from opentelemetry.test.test_base import TestBase


class TestMySQLClientIntegration(TestBase):
    # pylint: disable=invalid-name
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            MySQLClientInstrumentor().uninstrument()

    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test_instrumentor(self, mock_connect):
        MySQLClientInstrumentor().instrument()

        cnx = MySQLdb.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.mysqlclient
        )

        # check that no spans are generated after uninstrument
        MySQLClientInstrumentor().uninstrument()

        cnx = MySQLdb.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self, mock_connect):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        MySQLClientInstrumentor().instrument(tracer_provider=tracer_provider)

        cnx = MySQLdb.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(span.resource, resource)

    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test_instrument_connection(self, mock_connect):
        cnx = MySQLdb.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = MySQLClientInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("opentelemetry.instrumentation.dbapi.instrument_connection")
    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test_instrument_connection_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_instrument_connection,
    ):
        cnx = MySQLdb.connect(database="test")
        cnx = MySQLClientInstrumentor().instrument_connection(
            cnx,
            enable_commenter=True,
            commenter_options={"foo": True},
            enable_attribute_commenter=True,
        )
        cursor = cnx.cursor()
        cursor.execute("Select 1;")
        kwargs = mock_instrument_connection.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)
        self.assertEqual(kwargs["commenter_options"], {"foo": True})
        self.assertEqual(kwargs["enable_attribute_commenter"], True)

    def test_instrument_connection_with_dbapi_sqlcomment_enabled(self):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            cnx_proxy = MySQLClientInstrumentor().instrument_connection(
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
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_enabled_stmt_enabled(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            cnx_proxy = MySQLClientInstrumentor().instrument_connection(
                mock_connection,
                enable_commenter=True,
                enable_attribute_commenter=True,
            )
            cnx_proxy.cursor().execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_flags = format(span.get_span_context().trace_flags, "02x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_enabled_with_options(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            cnx_proxy = MySQLClientInstrumentor().instrument_connection(
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
            trace_flags = format(span.get_span_context().trace_flags, "02x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_threadsafety='123',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            cnx_proxy = MySQLClientInstrumentor().instrument_connection(
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
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test_instrument_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_wrap_connect,
    ):
        MySQLClientInstrumentor()._instrument(
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
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            MySQLClientInstrumentor()._instrument(
                enable_commenter=True,
            )
            cnx = mock_connect_module.connect(database="test")
            cursor = cnx.cursor()
            cursor.execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_flags = format(span.get_span_context().trace_flags, "02x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_with_dbapi_sqlcomment_enabled_stmt_enabled(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            MySQLClientInstrumentor()._instrument(
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
            trace_flags = format(span.get_span_context().trace_flags, "02x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-01'*/;",
            )

    def test_instrument_with_dbapi_sqlcomment_enabled_with_options(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            MySQLClientInstrumentor()._instrument(
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
            trace_flags = format(span.get_span_context().trace_flags, "02x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='MySQLdb%%3Afoobar',dbapi_threadsafety='123',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_connect_module = mock.MagicMock(
            __name__="MySQLdb",
            threadsafety="123",
            apilevel="123",
            paramstyle="test",
        )
        mock_connect_module._mysql.get_client_info.return_value = "foobaz"
        mock_cursor = mock_connect_module.connect().cursor()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        with (
            mock.patch(
                "opentelemetry.instrumentation.mysqlclient.MySQLdb",
                mock_connect_module,
            ),
            mock.patch(
                "opentelemetry.instrumentation.dbapi.util_version",
                return_value="foobar",
            ),
        ):
            MySQLClientInstrumentor()._instrument()
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
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test_uninstrument_connection(self, mock_connect):
        MySQLClientInstrumentor().instrument()
        cnx = MySQLdb.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        self.memory_exporter.clear()

        cnx = MySQLClientInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)
