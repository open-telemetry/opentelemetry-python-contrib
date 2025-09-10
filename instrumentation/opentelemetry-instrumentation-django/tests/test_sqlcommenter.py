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

# pylint: disable=no-name-in-module
from unittest.mock import MagicMock, patch

import pytest
from django import VERSION, conf
from django.http import HttpResponse
from django.test.utils import setup_test_environment, teardown_test_environment

from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware import (
    SqlCommenter,
    _QueryWrapper,
)
from opentelemetry.test.wsgitestutil import WsgiTestBase

DJANGO_2_0 = VERSION >= (2, 0)

_django_instrumentor = DjangoInstrumentor()


class TestMiddleware(WsgiTestBase):
    @classmethod
    def setUpClass(cls):
        conf.settings.configure(
            SQLCOMMENTER_WITH_FRAMEWORK=False,
            SQLCOMMENTER_WITH_DB_DRIVER=False,
        )
        super().setUpClass()

    def setUp(self):
        super().setUp()
        setup_test_environment()
        _django_instrumentor.instrument(is_sql_commentor_enabled=True)

    def tearDown(self):
        super().tearDown()
        teardown_test_environment()
        _django_instrumentor.uninstrument()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        conf.settings = conf.LazySettings()

    @patch(
        "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware.SqlCommenter"
    )
    def test_middleware_added(self, sqlcommenter_middleware):
        instance = sqlcommenter_middleware.return_value
        instance.get_response = HttpResponse()
        if DJANGO_2_0:
            middleware = conf.settings.MIDDLEWARE
        else:
            middleware = conf.settings.MIDDLEWARE_CLASSES

        self.assertTrue(
            "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware.SqlCommenter"
            in middleware
        )

    @patch(
        "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware.SqlCommenter"
    )
    def test_middleware_added_at_position(self, sqlcommenter_middleware):
        _django_instrumentor.uninstrument()
        if DJANGO_2_0:
            middleware = conf.settings.MIDDLEWARE
        else:
            middleware = conf.settings.MIDDLEWARE_CLASSES

        # adding two dummy middlewares
        temprory_middelware = "django.utils.deprecation.MiddlewareMixin"
        middleware.append(temprory_middelware)
        middleware.append(temprory_middelware)

        middleware_position = 1
        _django_instrumentor.instrument(
            is_sql_commentor_enabled=True,
            middleware_position=middleware_position,
        )
        instance = sqlcommenter_middleware.return_value
        instance.get_response = HttpResponse()
        self.assertEqual(
            middleware[middleware_position],
            "opentelemetry.instrumentation.django.middleware.otel_middleware.DjangoMiddleware",
        )
        self.assertEqual(
            middleware[middleware_position + 1],
            "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware.SqlCommenter",
        )

    @patch(
        "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware._get_opentelemetry_values"
    )
    def test_query_wrapper(self, trace_capture):
        requests_mock = MagicMock()
        requests_mock.resolver_match.view_name = "view"
        requests_mock.resolver_match.route = "route"
        requests_mock.resolver_match.app_name = "app"

        trace_capture.return_value = {
            "traceparent": "*traceparent='00-000000000000000000000000deadbeef-000000000000beef-00"
        }
        qw_instance = _QueryWrapper(requests_mock)
        execute_mock_obj = MagicMock()
        qw_instance(
            execute_mock_obj,
            "Select 1;",
            MagicMock("test"),
            MagicMock("test1"),
            MagicMock(),
        )
        output_sql = execute_mock_obj.call_args[0][0]
        self.assertEqual(
            output_sql,
            "Select 1 /*app_name='app',controller='view',route='route',traceparent='%%2Atraceparent%%3D%%2700-0000000"
            "00000000000000000deadbeef-000000000000beef-00'*/;",
        )

    @patch(
        "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware._get_opentelemetry_values"
    )
    def test_query_wrapper_non_string_queries(self, trace_capture):
        """Test that non-string queries and psycopg2 composable objects are handled correctly."""
        requests_mock = MagicMock()
        requests_mock.resolver_match.view_name = "view"
        requests_mock.resolver_match.route = "route"
        requests_mock.resolver_match.app_name = "app"

        trace_capture.return_value = {
            "traceparent": "*traceparent='00-000000000000000000000000deadbeef-000000000000beef-00"
        }
        qw_instance = _QueryWrapper(requests_mock)
        execute_mock_obj = MagicMock()

        input_query = MagicMock(as_string=lambda conn: "SELECT 2")
        expected_query_start = "SELECT 2"

        qw_instance(
            execute_mock_obj,
            input_query,
            MagicMock("test"),
            MagicMock("test1"),
            MagicMock(),
        )
        output_sql = execute_mock_obj.call_args[0][0]
        self.assertTrue(
            str(output_sql).startswith(str(expected_query_start)),
            f"Query should start with {expected_query_start!r}, got {output_sql!r}",
        )

    @patch(
        "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware._QueryWrapper"
    )
    def test_multiple_connection_support(self, query_wrapper):
        if not DJANGO_2_0:
            pytest.skip()

        requests_mock = MagicMock()
        get_response = MagicMock()

        sql_instance = SqlCommenter(get_response)
        sql_instance(requests_mock)

        # check if query_wrapper is added to the context for 2 databases
        self.assertEqual(query_wrapper.call_count, 2)

    @patch(
        "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware._get_opentelemetry_values"
    )
    def test_empty_sql(self, trace_capture):
        requests_mock = MagicMock()
        requests_mock.resolver_match.view_name = "view"
        requests_mock.resolver_match.route = "route"
        requests_mock.resolver_match.app_name = "app"

        trace_capture.return_value = {
            "traceparent": "*traceparent='00-000000000000000000000000deadbeef-000000000000beef-00"
        }
        qw_instance = _QueryWrapper(requests_mock)
        execute_mock_obj = MagicMock()
        qw_instance(
            execute_mock_obj,
            "",
            MagicMock("test"),
            MagicMock("test1"),
            MagicMock(),
        )
        output_sql = execute_mock_obj.call_args[0][0]
        self.assertEqual(
            output_sql,
            " /*app_name='app',controller='view',route='route',traceparent='%%2Atraceparent%%3D%%2700-0000000"
            "00000000000000000deadbeef-000000000000beef-00'*/",
        )
