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

# pylint: disable=too-many-lines

import logging
import re
from unittest import mock

from opentelemetry import context
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation import dbapi
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk import resources
from opentelemetry.semconv._incubating.attributes import net_attributes
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
from opentelemetry.test.test_base import TestBase


# pylint: disable=too-many-public-methods
class TestDBApiIntegration(TestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)

    def test_span_succeeded(self):
        connection_props = {
            "database": "testdatabase",
            "server_host": "testhost",
            "server_port": 123,
            "user": "testuser",
        }
        connection_attributes = {
            "database": "database",
            "port": "server_port",
            "host": "server_host",
            "user": "user",
        }
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
            connection_attributes,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, connection_props
        )
        cursor = mock_connection.cursor()
        cursor.execute("Test query", ("param1Value", False))
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "Test")
        self.assertIs(span.kind, trace_api.SpanKind.CLIENT)

        self.assertEqual(span.attributes[DB_SYSTEM], "testcomponent")
        self.assertEqual(span.attributes[DB_NAME], "testdatabase")
        self.assertEqual(span.attributes[DB_STATEMENT], "Test query")
        self.assertFalse("db.statement.parameters" in span.attributes)
        self.assertEqual(span.attributes[DB_USER], "testuser")
        self.assertEqual(span.attributes[NET_PEER_NAME], "testhost")
        self.assertEqual(span.attributes[NET_PEER_PORT], 123)
        self.assertIs(span.status.status_code, trace_api.StatusCode.UNSET)

    def test_span_name(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name", "testcomponent", {}
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.execute("Test query", ("param1Value", False))
        cursor.execute(
            """multi
        line
        query"""
        )
        cursor.execute("tab\tseparated query")
        cursor.execute("/* leading comment */ query")
        cursor.execute("/* leading comment */ query /* trailing comment */")
        cursor.execute("query /* trailing comment */")
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 6)
        self.assertEqual(spans_list[0].name, "Test")
        self.assertEqual(spans_list[1].name, "multi")
        self.assertEqual(spans_list[2].name, "tab")
        self.assertEqual(spans_list[3].name, "query")
        self.assertEqual(spans_list[4].name, "query")
        self.assertEqual(spans_list[5].name, "query")

    def test_span_succeeded_with_capture_of_statement_parameters(self):
        connection_props = {
            "database": "testdatabase",
            "server_host": "testhost",
            "server_port": 123,
            "user": "testuser",
        }
        connection_attributes = {
            "database": "database",
            "port": "server_port",
            "host": "server_host",
            "user": "user",
        }
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
            connection_attributes,
            capture_parameters=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, connection_props
        )
        cursor = mock_connection.cursor()
        cursor.execute("Test query", ("param1Value", False))
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "Test")
        self.assertIs(span.kind, trace_api.SpanKind.CLIENT)

        self.assertEqual(span.attributes[DB_SYSTEM], "testcomponent")
        self.assertEqual(span.attributes[DB_NAME], "testdatabase")
        self.assertEqual(span.attributes[DB_STATEMENT], "Test query")
        self.assertEqual(
            span.attributes["db.statement.parameters"],
            "('param1Value', False)",
        )
        self.assertEqual(span.attributes[DB_USER], "testuser")
        self.assertEqual(
            span.attributes[net_attributes.NET_PEER_NAME], "testhost"
        )
        self.assertEqual(span.attributes[net_attributes.NET_PEER_PORT], 123)
        self.assertIs(span.status.status_code, trace_api.StatusCode.UNSET)

    def test_span_not_recording(self):
        connection_props = {
            "database": "testdatabase",
            "server_host": "testhost",
            "server_port": 123,
            "user": "testuser",
        }
        connection_attributes = {
            "database": "database",
            "port": "server_port",
            "host": "server_host",
            "user": "user",
        }
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
            connection_attributes,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, connection_props
        )
        cursor = mock_connection.cursor()
        cursor.execute("Test query", ("param1Value", False))
        self.assertFalse(mock_span.is_recording())
        self.assertTrue(mock_span.is_recording.called)
        self.assertFalse(mock_span.set_attribute.called)
        self.assertFalse(mock_span.set_status.called)

    def test_span_failed(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name", "testcomponent"
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        with self.assertRaises(Exception):
            cursor.execute("Test query", throw_exception=True)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.attributes[DB_STATEMENT], "Test query")
        self.assertIs(span.status.status_code, trace_api.StatusCode.ERROR)
        self.assertEqual(span.status.description, "Exception: Test Exception")

    def test_custom_tracer_provider_dbapi(self):
        resource = resources.Resource.create({"db-resource-key": "value"})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
            tracer_provider=tracer_provider,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        with self.assertRaises(Exception):
            cursor.execute("Test query", throw_exception=True)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.resource.attributes["db-resource-key"], "value")
        self.assertIs(span.status.status_code, trace_api.StatusCode.ERROR)

    def test_no_op_tracer_provider(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
            tracer_provider=trace_api.NoOpTracerProvider(),
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Test query")
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_suppress_instrumentation(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        with suppress_instrumentation():
            cursor = mock_connection.cursor()
            cursor.execute("Test query", ("param1Value", False))

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_commenter_options_propagation(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "testcomponent",
            commenter_options={"opentelemetry_values": False},
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        with self.assertRaises(Exception):
            cursor.execute("SELECT 1", throw_exception=True)
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.attributes.get("db.system"), "testcomponent")
        self.assertIn("opentelemetry_values", db_integration.commenter_options)
        self.assertFalse(
            db_integration.commenter_options["opentelemetry_values"]
        )

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    def test_trace_integration_passes_commenter_options(
        self, mock_wrap_connect
    ):
        fake_connect_module = mock.Mock()
        fake_options = {"opentelemetry_values": False, "foo": "bar"}
        dbapi.trace_integration(
            connect_module=fake_connect_module,
            connect_method_name="connect",
            database_system="testdb",
            commenter_options=fake_options,
        )
        mock_wrap_connect.assert_called_once()
        _, _, kwargs = mock_wrap_connect.mock_calls[0]

        self.assertIn("commenter_options", kwargs)
        self.assertEqual(kwargs["commenter_options"], fake_options)

    def test_executemany(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name", "testcomponent"
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Test query")
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.attributes[DB_STATEMENT], "Test query")

    def test_executemany_comment(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_executemany_comment_stmt_enabled(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_comment_non_pep_249_compliant(self):
        class MockConnectModule:
            def __getattr__(self, name):
                if name == "__name__":
                    return "test"
                if name == "__version__":
                    return mock.MagicMock()
                if name == "__libpq_version__":
                    return 123
                raise AttributeError("attribute missing")

        connect_module = MockConnectModule()
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            connect_module=connect_module,
            commenter_options={"db_driver": False},
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_level='1.0',dbapi_threadsafety='unknown',driver_paramstyle='unknown',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_executemany_comment_non_pep_249_compliant_stmt_enabled(self):
        class MockConnectModule:
            def __getattr__(self, name):
                if name == "__name__":
                    return "test"
                if name == "__version__":
                    return mock.MagicMock()
                if name == "__libpq_version__":
                    return 123
                raise AttributeError("attribute missing")

        connect_module = MockConnectModule()
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            connect_module=connect_module,
            commenter_options={"db_driver": False},
            enable_attribute_commenter=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_level='1.0',dbapi_threadsafety='unknown',driver_paramstyle='unknown',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*dbapi_level='1.0',dbapi_threadsafety='unknown',driver_paramstyle='unknown',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_comment_stmt_enabled_matches_db_statement_attribute(
        self,
    ):
        connect_module = mock.MagicMock()
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/",
        )

        cursor_span_id = re.search(r"[a-zA-Z0-9_]{16}", cursor.query).group()
        db_statement_span_id = re.search(
            r"[a-zA-Z0-9_]{16}", span.attributes[DB_STATEMENT]
        ).group()
        self.assertEqual(cursor_span_id, db_statement_span_id)

    def test_compatible_build_version_psycopg2_libpq(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.side_effect = AttributeError
        connect_module.__libpq_version__ = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_compatible_build_version_psycopg_libpq(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_no_libpq_version_when_we_dont_instrument_the_root_module(
        self,
    ):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.side_effect = AttributeError
        connect_module.__libpq_version__ = None
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_psycopg2_integration_comment(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "psycopg2"
        connect_module.__version__ = "1.2.3"
        connect_module.pq.version.side_effect = AttributeError
        connect_module.__libpq_version__ = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='psycopg2%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_executemany_psycopg2_integration_comment_stmt_enabled(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "psycopg2"
        connect_module.__version__ = "1.2.3"
        connect_module.pq.version.side_effect = AttributeError
        connect_module.__libpq_version__ = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='psycopg2%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*db_driver='psycopg2%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_psycopg_integration_comment(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "psycopg"
        connect_module.__version__ = "1.2.3"
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='psycopg%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_executemany_psycopg_integration_comment_stmt_enabled(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "psycopg"
        connect_module.__version__ = "1.2.3"
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='psycopg%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*db_driver='psycopg%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_mysqlconnector_integration_comment(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "mysql.connector"
        connect_module.__version__ = "1.2.3"
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='mysql.connector%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='1.2.3',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_executemany_mysqlconnector_integration_comment_stmt_enabled(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "mysql.connector"
        connect_module.__version__ = "1.2.3"
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='mysql.connector%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='1.2.3',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*db_driver='mysql.connector%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='1.2.3',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    @mock.patch("opentelemetry.instrumentation.dbapi.util_version")
    def test_executemany_mysqlclient_integration_comment(
        self,
        mock_dbapi_util_version,
    ):
        mock_dbapi_util_version.return_value = "1.2.3"
        connect_module = mock.MagicMock()
        connect_module.__name__ = "MySQLdb"
        connect_module.__version__ = "1.2.3"
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"
        connect_module._mysql = mock.MagicMock()
        connect_module._mysql.get_client_info = mock.MagicMock(
            return_value="123"
        )

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='MySQLdb%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='123',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    @mock.patch("opentelemetry.instrumentation.dbapi.util_version")
    def test_executemany_mysqlclient_integration_comment_stmt_enabled(
        self,
        mock_dbapi_util_version,
    ):
        mock_dbapi_util_version.return_value = "1.2.3"
        connect_module = mock.MagicMock()
        connect_module.__name__ = "MySQLdb"
        connect_module.__version__ = "1.2.3"
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"
        connect_module._mysql = mock.MagicMock()
        connect_module._mysql.get_client_info = mock.MagicMock(
            return_value="123"
        )

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='MySQLdb%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='123',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*db_driver='MySQLdb%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='123',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_pymysql_integration_comment(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "pymysql"
        connect_module.__version__ = "1.2.3"
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"
        connect_module.get_client_info = mock.MagicMock(return_value="123")

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='pymysql%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='123',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

    def test_executemany_pymysql_integration_comment_stmt_enabled(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "pymysql"
        connect_module.__version__ = "1.2.3"
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"
        connect_module.get_client_info = mock.MagicMock(return_value="123")

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            commenter_options={"db_driver": True, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*db_driver='pymysql%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='123',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*db_driver='pymysql%%3A1.2.3',dbapi_threadsafety=123,driver_paramstyle='test',mysql_client_version='123',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_executemany_flask_integration_comment(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
        )
        current_context = context.get_current()
        sqlcommenter_context = context.set_value(
            "SQLCOMMENTER_ORM_TAGS_AND_VALUES", {"flask": 1}, current_context
        )
        token = context.attach(sqlcommenter_context)

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',flask=1,libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1;",
        )

        context.detach(token)

    def test_executemany_flask_integration_comment_stmt_enabled(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = mock.MagicMock()
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = 123
        connect_module.threadsafety = 123
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "postgresql",
            enable_commenter=True,
            commenter_options={"db_driver": False, "dbapi_level": False},
            connect_module=connect_module,
            enable_attribute_commenter=True,
        )
        current_context = context.get_current()
        sqlcommenter_context = context.set_value(
            "SQLCOMMENTER_ORM_TAGS_AND_VALUES", {"flask": 1}, current_context
        )
        token = context.attach(sqlcommenter_context)

        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.executemany("Select 1;")
        self.assertRegex(
            cursor.query,
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',flask=1,libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertRegex(
            span.attributes[DB_STATEMENT],
            r"Select 1 /\*dbapi_threadsafety=123,driver_paramstyle='test',flask=1,libpq_version=123,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

        context.detach(token)

    def test_callproc(self):
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name", "testcomponent"
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor.callproc("Test stored procedure")
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Test stored procedure",
        )

    @mock.patch("opentelemetry.instrumentation.dbapi")
    def test_wrap_connect(self, mock_dbapi):
        dbapi.wrap_connect(self.tracer, mock_dbapi, "connect", "-")
        connection = mock_dbapi.connect()
        self.assertEqual(mock_dbapi.connect.call_count, 1)
        self.assertIsInstance(connection.__wrapped__, mock.Mock)

    @mock.patch("opentelemetry.instrumentation.dbapi")
    def test_unwrap_connect(self, mock_dbapi):
        dbapi.wrap_connect(self.tracer, mock_dbapi, "connect", "-")
        connection = mock_dbapi.connect()
        self.assertEqual(mock_dbapi.connect.call_count, 1)

        dbapi.unwrap_connect(mock_dbapi, "connect")
        connection = mock_dbapi.connect()
        self.assertEqual(mock_dbapi.connect.call_count, 2)
        self.assertIsInstance(connection, mock.Mock)

    def test_instrument_connection(self):
        mocked_conn = MockConnection("dbname", "999", "dbhost", "dbuser")
        # Avoid get_attributes failing because can't concatenate mock
        connection2 = dbapi.instrument_connection(
            "instrumenting_module_test_name", mocked_conn, "dbname"
        )
        self.assertIs(connection2.__wrapped__, mocked_conn)

    @mock.patch("opentelemetry.instrumentation.dbapi.DatabaseApiIntegration")
    def test_instrument_connection_kwargs_defaults(self, mock_dbapiint):
        mocked_conn = MockConnection("dbname", "999", "dbhost", "dbuser")
        dbapi.instrument_connection(
            "instrumenting_module_test_name", mocked_conn, "foo"
        )
        kwargs = mock_dbapiint.call_args[1]
        self.assertEqual(kwargs["connection_attributes"], None)
        self.assertEqual(kwargs["version"], "")
        self.assertEqual(kwargs["tracer_provider"], None)
        self.assertEqual(kwargs["capture_parameters"], False)
        self.assertEqual(kwargs["enable_commenter"], False)
        self.assertEqual(kwargs["commenter_options"], None)
        self.assertEqual(kwargs["connect_module"], None)
        self.assertEqual(kwargs["enable_attribute_commenter"], False)

    @mock.patch("opentelemetry.instrumentation.dbapi.DatabaseApiIntegration")
    def test_instrument_connection_kwargs_provided(self, mock_dbapiint):
        mocked_conn = MockConnection("dbname", "999", "dbhost", "dbuser")
        mock_tracer_provider = mock.MagicMock()
        mock_connect_module = mock.MagicMock()
        dbapi.instrument_connection(
            "instrumenting_module_test_name",
            mocked_conn,
            "foo",
            connection_attributes={"foo": "bar"},
            version="test",
            tracer_provider=mock_tracer_provider,
            capture_parameters=True,
            enable_commenter=True,
            commenter_options={"foo": "bar"},
            connect_module=mock_connect_module,
            enable_attribute_commenter=True,
        )
        kwargs = mock_dbapiint.call_args[1]
        self.assertEqual(kwargs["connection_attributes"], {"foo": "bar"})
        self.assertEqual(kwargs["version"], "test")
        self.assertIs(kwargs["tracer_provider"], mock_tracer_provider)
        self.assertEqual(kwargs["capture_parameters"], True)
        self.assertEqual(kwargs["enable_commenter"], True)
        self.assertEqual(kwargs["commenter_options"], {"foo": "bar"})
        self.assertIs(kwargs["connect_module"], mock_connect_module)
        self.assertEqual(kwargs["enable_attribute_commenter"], True)

    def test_instrument_connection_db_api_integration_factory(self):
        mocked_conn = MockConnection("dbname", "999", "dbhost", "dbuser")

        class DBApiIntegrationTestClass(dbapi.DatabaseApiIntegration):
            pass

        conn = dbapi.instrument_connection(
            "instrumenting_module_test_name",
            mocked_conn,
            "dbsystem",
            db_api_integration_factory=DBApiIntegrationTestClass,
        )
        self.assertIsInstance(
            conn._self_db_api_integration, DBApiIntegrationTestClass
        )

    def test_uninstrument_connection(self):
        mocked_conn = MockConnection("dbname", "999", "dbhost", "dbuser")
        connection2 = dbapi.instrument_connection(
            "instrumenting_module_test_name", mocked_conn, "-"
        )
        self.assertIs(connection2.__wrapped__, mocked_conn)

        connection3 = dbapi.uninstrument_connection(connection2)
        self.assertIs(connection3, mocked_conn)

        with self.assertLogs(level=logging.WARNING):
            connection4 = dbapi.uninstrument_connection(mocked_conn)
        self.assertIs(connection4, mocked_conn)

    def test_non_string_sql_conversion(self):
        """Test that non-string SQL statements are converted to strings before adding comments."""
        # Create a mock connect_module with required attributes
        connect_module = mock.MagicMock()
        connect_module.__name__ = "test"
        connect_module.__version__ = "1.0"
        connect_module.pq.version.return_value = 123
        connect_module.apilevel = "2.0"
        connect_module.threadsafety = 1
        connect_module.paramstyle = "test"

        db_integration = dbapi.DatabaseApiIntegration(
            "testname",
            "postgresql",
            enable_commenter=True,
            connect_module=connect_module,
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()

        input_sql = mock.MagicMock(as_string=lambda conn: "SELECT 2")
        expected_sql = "SELECT 2"

        cursor.executemany(input_sql)
        # Extract the SQL part (before the comment)
        actual_sql = cursor.query.split("/*")[0].strip()
        self.assertEqual(actual_sql, expected_sql)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    def test_capture_mysql_version_primary_success(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "mysql.connector"
        connect_module.__version__ = "2.2.9"
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            connect_module=connect_module,
        )
        mock_cursor = mock.MagicMock()
        mock_cursor._cnx._cmysql.get_client_info.return_value = "8.0.32"
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor._cnx = mock_cursor._cnx
        cursor.execute("SELECT 1;")
        mock_cursor._cnx._cmysql.get_client_info.assert_called_once()
        self.assertEqual(
            db_integration.commenter_data["mysql_client_version"], "8.0.32"
        )

    def test_capture_mysql_version_fallback_success(self):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "mysql.connector"
        connect_module.__version__ = "2.2.9"
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            connect_module=connect_module,
        )
        mock_cursor = mock.MagicMock()
        mock_cursor._cnx._cmysql.get_client_info.side_effect = AttributeError(
            "Primary method failed"
        )
        mock_cursor._connection._cmysql.get_client_info.return_value = "8.0.33"
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor._cnx = mock_cursor._cnx
        cursor._connection = mock_cursor._connection
        cursor.execute("SELECT 1;")
        mock_cursor._cnx._cmysql.get_client_info.assert_called_once()
        mock_cursor._connection._cmysql.get_client_info.assert_called_once()
        self.assertEqual(
            db_integration.commenter_data["mysql_client_version"], "8.0.33"
        )

    @mock.patch("opentelemetry.instrumentation.dbapi._logger")
    def test_capture_mysql_version_fallback(self, mock_logger):
        connect_module = mock.MagicMock()
        connect_module.__name__ = "mysql.connector"
        connect_module.__version__ = "2.2.9"
        db_integration = dbapi.DatabaseApiIntegration(
            "instrumenting_module_test_name",
            "mysql",
            enable_commenter=True,
            connect_module=connect_module,
        )
        mock_cursor = mock.MagicMock()
        mock_cursor._cnx._cmysql.get_client_info.side_effect = AttributeError(
            "Primary method failed"
        )
        mock_cursor._connection._cmysql.get_client_info.side_effect = (
            AttributeError("Fallback method failed")
        )
        mock_connection = db_integration.wrapped_connection(
            mock_connect, {}, {}
        )
        cursor = mock_connection.cursor()
        cursor._cnx = mock_cursor._cnx
        cursor._connection = mock_cursor._connection
        cursor.execute("SELECT 1;")
        mock_cursor._cnx._cmysql.get_client_info.assert_called_once()
        mock_cursor._connection._cmysql.get_client_info.assert_called_once()
        mock_logger.debug.assert_called_once()
        self.assertEqual(
            db_integration.commenter_data["mysql_client_version"], "unknown"
        )


# pylint: disable=unused-argument
def mock_connect(*args, **kwargs):
    database = kwargs.get("database")
    server_host = kwargs.get("server_host")
    server_port = kwargs.get("server_port")
    user = kwargs.get("user")
    return MockConnection(database, server_port, server_host, user)


class MockConnection:
    def __init__(self, database, server_port, server_host, user):
        self.database = database
        self.server_port = server_port
        self.server_host = server_host
        self.user = user

    # pylint: disable=no-self-use
    def cursor(self):
        return MockCursor()


class MockCursor:
    def __init__(self) -> None:
        self.query = ""
        self.params = None
        self.connection = None
        # Mock mysql.connector modules and method
        self._cnx = mock.MagicMock()
        self._cnx._cmysql = mock.MagicMock()
        self._cnx._cmysql.get_client_info = mock.MagicMock(
            return_value="1.2.3"
        )

    # pylint: disable=unused-argument, no-self-use
    def execute(self, query, params=None, throw_exception=False):
        if throw_exception:
            # pylint: disable=broad-exception-raised
            raise Exception("Test Exception")

    # pylint: disable=unused-argument, no-self-use
    def executemany(self, query, params=None, throw_exception=False):
        if throw_exception:
            # pylint: disable=broad-exception-raised
            raise Exception("Test Exception")
        self.query = query
        self.params = params

    # pylint: disable=unused-argument, no-self-use
    def callproc(self, query, params=None, throw_exception=False):
        if throw_exception:
            # pylint: disable=broad-exception-raised
            raise Exception("Test Exception")
