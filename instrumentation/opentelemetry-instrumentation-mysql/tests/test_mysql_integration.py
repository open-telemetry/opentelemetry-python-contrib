# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
from unittest import mock

import mysql.connector

import opentelemetry.instrumentation.mysql
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.mysql import MySQLInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
    DB_USER,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase


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


def connect_and_execute_query():
    cnx = mysql.connector.connect(database="test")
    cursor = cnx.cursor()
    query = "SELECT * FROM test"
    cursor.execute(query)

    return cnx, query


def make_mysql_connection_mock():
    cnx = mock.MagicMock()
    cnx.database = "test"
    cnx.server_host = "localhost"
    cnx.server_port = 3306
    cnx.user = "testuser"

    cursor = mock.MagicMock()
    cursor._cnx = cnx

    cnx.cursor.return_value = cursor
    return cnx


def make_mysql_commenter_mocks(client_version="foobaz"):
    """Create mock objects for MySQL connector with SQL commenter support.

    Args:
        client_version: The MySQL client version string to return from get_client_info()

    Returns:
        Tuple of (mock_connect_module, mock_connection, mock_cursor)
    """
    mock_connect_module = mock.MagicMock(
        __name__="mysql.connector",
        __version__="foobar",
        threadsafety="123",
        apilevel="123",
        paramstyle="test",
    )
    mock_connection = mock.MagicMock()
    mock_connection.database = "test"
    mock_connection.server_host = "localhost"
    mock_connection.server_port = 3306

    mock_cursor = mock_connect_module.connect().cursor()
    mock_cursor._cnx = mock_connection
    mock_cursor._cnx._cmysql.get_client_info.return_value = client_version

    mock_connection.cursor.return_value = mock_cursor
    mock_connect_module.connect.return_value = mock_connection

    return mock_connect_module, mock_connection, mock_cursor


class TestMysqlIntegration(TestBase):
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            MySQLInstrumentor().uninstrument()

    @mock.patch("mysql.connector.connect")
    # pylint: disable=unused-argument
    def test_instrumentor(self, mock_connect):
        mock_connect.return_value = make_mysql_connection_mock()
        MySQLInstrumentor().instrument()

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.mysql
        )

        # check that no spans are generated after uninstrumen
        MySQLInstrumentor().uninstrument()

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("mysql.connector.connect")
    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self, mock_connect):
        mock_connect.return_value = make_mysql_connection_mock()
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        MySQLInstrumentor().instrument(tracer_provider=tracer_provider)
        connect_and_execute_query()

        span_list = exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        span = span_list[0]

        self.assertIs(span.resource, resource)

    @mock.patch("mysql.connector.connect")
    # pylint: disable=unused-argument
    def test_instrument_connection(self, mock_connect):
        mock_connect.return_value = make_mysql_connection_mock()
        cnx, query = connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = MySQLInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("mysql.connector.connect")
    def test_instrument_connection_no_op_tracer_provider(self, mock_connect):
        mock_connect.return_value = make_mysql_connection_mock()
        tracer_provider = trace_api.NoOpTracerProvider()
        MySQLInstrumentor().instrument(tracer_provider=tracer_provider)
        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    @mock.patch("opentelemetry.instrumentation.dbapi.instrument_connection")
    @mock.patch("mysql.connector")
    # pylint: disable=unused-argument
    def test_instrument_connection_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_instrument_connection,
    ):
        cnx = mysql.connector.connect(database="test")
        cnx = MySQLInstrumentor().instrument_connection(
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

    @mock.patch("opentelemetry.instrumentation.mysql.dbapi.wrap_connect")
    def test_instrument_capture_parameters_default(self, mock_wrap_connect):
        MySQLInstrumentor().instrument()
        kwargs = mock_wrap_connect.call_args[1]
        self.assertEqual(kwargs["capture_parameters"], False)

    @mock.patch("opentelemetry.instrumentation.mysql.dbapi.wrap_connect")
    def test_instrument_capture_parameters_enabled(self, mock_wrap_connect):
        MySQLInstrumentor().instrument(capture_parameters=True)
        kwargs = mock_wrap_connect.call_args[1]
        self.assertEqual(kwargs["capture_parameters"], True)

    @mock.patch("opentelemetry.instrumentation.dbapi.instrument_connection")
    @mock.patch("mysql.connector")
    # pylint: disable=unused-argument
    def test_instrument_connection_capture_parameters_default(
        self,
        mock_connect,
        mock_instrument_connection,
    ):
        cnx = mysql.connector.connect(database="test")
        MySQLInstrumentor().instrument_connection(cnx)
        kwargs = mock_instrument_connection.call_args[1]
        self.assertEqual(kwargs["capture_parameters"], False)

    @mock.patch("opentelemetry.instrumentation.dbapi.instrument_connection")
    @mock.patch("mysql.connector")
    # pylint: disable=unused-argument
    def test_instrument_connection_capture_parameters_enabled(
        self,
        mock_connect,
        mock_instrument_connection,
    ):
        cnx = mysql.connector.connect(database="test")
        MySQLInstrumentor().instrument_connection(
            cnx,
            capture_parameters=True,
        )
        kwargs = mock_instrument_connection.call_args[1]
        self.assertEqual(kwargs["capture_parameters"], True)

    def test_instrument_connection_with_dbapi_sqlcomment_enabled(self):
        mock_connect_module, mock_connection, mock_cursor = (
            make_mysql_commenter_mocks()
        )

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            cnx_proxy = MySQLInstrumentor().instrument_connection(
                mock_connection,
                enable_commenter=True,
            )
            cnx_proxy.cursor().execute("Select 1;")

            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_flags = format(span.get_span_context().trace_flags, "02x")
            self.assertEqual(
                mock_cursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_enabled_stmt_enabled(
        self,
    ):
        mock_connect_module, mock_connection, mock_cursor = (
            make_mysql_commenter_mocks()
        )

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            cnx_proxy = MySQLInstrumentor().instrument_connection(
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
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_enabled_with_options(
        self,
    ):
        mock_connect_module, mock_connection, mock_cursor = (
            make_mysql_commenter_mocks()
        )

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            cnx_proxy = MySQLInstrumentor().instrument_connection(
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
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_threadsafety='123',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_connection_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_connect_module, mock_connection, mock_cursor = (
            make_mysql_commenter_mocks()
        )

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            cnx_proxy = MySQLInstrumentor().instrument_connection(
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
    @mock.patch("mysql.connector")
    # pylint: disable=unused-argument
    def test_instrument_enable_commenter_dbapi_kwargs(
        self,
        mock_connect,
        mock_wrap_connect,
    ):
        MySQLInstrumentor()._instrument(
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
        mock_connect_module, _, mock_cursor = make_mysql_commenter_mocks()

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            MySQLInstrumentor()._instrument(
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
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_with_dbapi_sqlcomment_enabled_stmt_enabled(
        self,
    ):
        mock_connect_module, _, mock_cursor = make_mysql_commenter_mocks()

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            MySQLInstrumentor()._instrument(
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
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )

    def test_instrument_with_dbapi_sqlcomment_enabled_with_options(
        self,
    ):
        mock_connect_module, _, mock_cursor = make_mysql_commenter_mocks()

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            MySQLInstrumentor()._instrument(
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
                f"Select 1 /*db_driver='mysql.connector%%3Afoobar',dbapi_threadsafety='123',mysql_client_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags}'*/;",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1;",
            )

    def test_instrument_with_dbapi_sqlcomment_not_enabled_default(
        self,
    ):
        mock_connect_module, _, mock_cursor = make_mysql_commenter_mocks()

        with mock.patch(
            "opentelemetry.instrumentation.mysql.mysql.connector",
            mock_connect_module,
        ):
            MySQLInstrumentor()._instrument()
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

    @mock.patch("mysql.connector.connect")
    # pylint: disable=unused-argument
    def test_uninstrument_connection(self, mock_connect):
        mock_connect.return_value = make_mysql_connection_mock()
        MySQLInstrumentor().instrument()
        cnx, query = connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = MySQLInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("mysql.connector.connect")
    def test_semconv_stable(self, mock_connect):
        """database,http opt-in emits only stable attributes."""
        with use_semconv_opt_in("database,http"):
            mock_connect.return_value = make_mysql_connection_mock()
            MySQLInstrumentor().instrument()

            connect_and_execute_query()

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 1)
            span = spans_list[0]

            self.assertEqual(span.attributes[DB_SYSTEM_NAME], "mysql")
            self.assertEqual(span.attributes[DB_NAMESPACE], "test")
            self.assertEqual(
                span.attributes[DB_QUERY_TEXT], "SELECT * FROM test"
            )
            self.assertEqual(span.attributes[SERVER_ADDRESS], "localhost")
            self.assertEqual(span.attributes[SERVER_PORT], 3306)
            self.assertNotIn(DB_SYSTEM, span.attributes)
            self.assertNotIn(DB_NAME, span.attributes)
            self.assertNotIn(DB_STATEMENT, span.attributes)
            self.assertNotIn(DB_USER, span.attributes)
            self.assertNotIn(NET_PEER_NAME, span.attributes)
            self.assertNotIn(NET_PEER_PORT, span.attributes)

    @mock.patch("mysql.connector.connect")
    def test_semconv_dup(self, mock_connect):
        """database/dup,http/dup opt-in emits both legacy and stable attributes."""
        with use_semconv_opt_in("database/dup,http/dup"):
            mock_connect.return_value = make_mysql_connection_mock()
            MySQLInstrumentor().instrument()

            connect_and_execute_query()

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 1)
            span = spans_list[0]

            self.assertEqual(span.attributes[DB_SYSTEM], "mysql")
            self.assertEqual(span.attributes[DB_SYSTEM_NAME], "mysql")
            self.assertEqual(span.attributes[DB_NAME], "test")
            self.assertEqual(span.attributes[DB_NAMESPACE], "test")
            self.assertEqual(
                span.attributes[DB_STATEMENT], "SELECT * FROM test"
            )
            self.assertEqual(
                span.attributes[DB_QUERY_TEXT], "SELECT * FROM test"
            )
            self.assertEqual(span.attributes[DB_USER], "testuser")
            self.assertEqual(span.attributes[NET_PEER_NAME], "localhost")
            self.assertEqual(span.attributes[NET_PEER_PORT], 3306)
            self.assertEqual(span.attributes[SERVER_ADDRESS], "localhost")
            self.assertEqual(span.attributes[SERVER_PORT], 3306)
