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
from opentelemetry.test.test_base import TestBase


class TestMySQLClientIntegration(TestBase):
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
        self.assertEqualSpanInstrumentationInfo(
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
        )
        cursor = cnx.cursor()
        cursor.execute("Select 1;")
        kwargs = mock_instrument_connection.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)
        self.assertEqual(kwargs["commenter_options"], {"foo": True})

    def test_instrument_connection_with_dbapi_sqlcomment_enabled(self):
        mock_cursor = mock.MagicMock()
        mock_cursor.execute = mock.MagicMock()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        mock_connect_module = mock.MagicMock()
        mock_connect_module.__name__ = "MySQLdb"
        mock_connect_module.threadsafety = "123"
        mock_connect_module.apilevel = "123"
        mock_connect_module.paramstyle = "test"
        mock_connect_module._mysql.get_client_info = mock.Mock(
            return_value="foobaz"
        )
        mock_connect_module.connect = mock.Mock(return_value=mock_connection)

        with mock.patch(
            "opentelemetry.instrumentation.mysqlclient.MySQLdb",
            mock_connect_module,
        ), mock.patch(
            "opentelemetry.instrumentation.dbapi.util_version",
            return_value="foobar",
        ):
            cnx_proxy = MySQLClientInstrumentor().instrument_connection(
                mock_connection,
                enable_commenter=True,
                commenter_options={"foo": True},
            )
            cnx_proxy.cursor().execute("Select 1;")
            self.assertRegex(
                mock_cursor.execute.call_args[0][0],
                r"Select 1 /\*db_driver='MySQLdb%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_cursor = mock.MagicMock()
        mock_cursor.execute = mock.MagicMock()
        mock_connection = mock.MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        mock_connect_module = mock.MagicMock()
        mock_connect_module.__name__ = "MySQLdb"
        mock_connect_module.threadsafety = "123"
        mock_connect_module.apilevel = "123"
        mock_connect_module.paramstyle = "test"
        mock_connect_module._mysql.get_client_info = mock.Mock(
            return_value="foobaz"
        )

        mock_connect_module.connect = mock.Mock(return_value=mock_connection)

        with mock.patch(
            "opentelemetry.instrumentation.mysqlclient.MySQLdb",
            mock_connect_module,
        ), mock.patch(
            "opentelemetry.instrumentation.dbapi.util_version",
            return_value="foobar",
        ):
            cnx_proxy = MySQLClientInstrumentor().instrument_connection(
                mock_connection,
            )
            cnx_proxy.cursor().execute("Select 1;")
            self.assertRegex(
                mock_cursor.execute.call_args[0][0],
                r"Select 1;",
            )

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    @mock.patch("MySQLdb.connect")
    # pylint: disable=unused-argument
    def test__instrument_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_wrap_connect,
    ):
        MySQLClientInstrumentor()._instrument(
            enable_commenter=True,
            commenter_options={"foo": True},
        )
        kwargs = mock_wrap_connect.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)
        self.assertEqual(kwargs["commenter_options"], {"foo": True})

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
