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

from sys import modules
from unittest.mock import Mock, patch

from django import VERSION, conf
from django.test import SimpleTestCase
from django.test.utils import setup_test_environment, teardown_test_environment
from django.urls import re_path
import pytest

from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util.http import get_excluded_urls, get_traced_request_attrs

# pylint: disable=import-error
from .views import (
    async_error,
    async_excluded,
    async_excluded_noarg,
    async_excluded_noarg2,
    async_route_span_name,
    async_traced,
    async_traced_template,
)

DJANGO_3_1 = VERSION >= (3, 1)

if DJANGO_3_1:
    from django.test.client import AsyncClient
else:
    AsyncClient = None

urlpatterns = [
    re_path(r"^traced/", async_traced),
    re_path(r"^route/(?P<year>[0-9]{4})/template/$", async_traced_template),
    re_path(r"^error/", async_error),
    re_path(r"^excluded_arg/", async_excluded),
    re_path(r"^excluded_noarg/", async_excluded_noarg),
    re_path(r"^excluded_noarg2/", async_excluded_noarg2),
    re_path(r"^span_name/([0-9]{4})/$", async_route_span_name),
]
_django_instrumentor = DjangoInstrumentor()


@pytest.mark.skipif(not DJANGO_3_1, reason="AsyncClient implemented since Django 3.1")
class TestMiddlewareAsgi(SimpleTestCase, TestBase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        conf.settings.configure(ROOT_URLCONF=modules[__name__])

    def setUp(self):
        super().setUp()
        setup_test_environment()
        _django_instrumentor.instrument()
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_DJANGO_EXCLUDED_URLS": "http://testserver/excluded_arg/123,excluded_noarg",
                "OTEL_PYTHON_DJANGO_TRACED_REQUEST_ATTRS": "path_info,content_type,non_existing_variable",
            },
        )
        self.env_patch.start()
        self.exclude_patch = patch(
            "opentelemetry.instrumentation.django.middleware._DjangoMiddleware._excluded_urls",
            get_excluded_urls("DJANGO"),
        )
        self.traced_patch = patch(
            "opentelemetry.instrumentation.django.middleware._DjangoMiddleware._traced_request_attrs",
            get_traced_request_attrs("DJANGO"),
        )
        self.exclude_patch.start()
        self.traced_patch.start()

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        self.exclude_patch.stop()
        self.traced_patch.stop()
        teardown_test_environment()
        _django_instrumentor.uninstrument()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        conf.settings = conf.LazySettings()

    @classmethod
    def _add_databases_failures(cls):
        # Disable databases.
        pass

    @classmethod
    def _remove_databases_failures(cls):
        # Disable databases.
        pass

    @pytest.mark.skip(reason="TODO")
    async def test_templated_route_get(self):
        await self.async_client.get("/route/2020/template/")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]

        self.assertEqual(span.name, "^route/(?P<year>[0-9]{4})/template/$")
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["http.method"], "GET")
        self.assertEqual(
            span.attributes["http.url"],
            "http://testserver/route/2020/template/",
        )
        self.assertEqual(
            span.attributes["http.route"],
            "^route/(?P<year>[0-9]{4})/template/$",
        )
        self.assertEqual(span.attributes["http.scheme"], "http")
        self.assertEqual(span.attributes["http.status_code"], 200)
        self.assertEqual(span.attributes["http.status_text"], "OK")

    @pytest.mark.skip(reason="TODO")
    async def test_traced_get(self):
        await self.async_client.get("/traced/")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]

        self.assertEqual(span.name, "^traced/")
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["http.method"], "GET")
        self.assertEqual(
            span.attributes["http.url"], "http://testserver/traced/"
        )
        self.assertEqual(span.attributes["http.route"], "^traced/")
        self.assertEqual(span.attributes["http.scheme"], "http")
        self.assertEqual(span.attributes["http.status_code"], 200)
        self.assertEqual(span.attributes["http.status_text"], "OK")

    async def test_not_recording(self):
        mock_tracer = Mock()
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            await self.async_client.get("/traced/")
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    @pytest.mark.skip(reason="TODO")
    async def test_traced_post(self):
        await self.async_client.post("/traced/")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]

        self.assertEqual(span.name, "^traced/")
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(span.attributes["http.method"], "POST")
        self.assertEqual(
            span.attributes["http.url"], "http://testserver/traced/"
        )
        self.assertEqual(span.attributes["http.route"], "^traced/")
        self.assertEqual(span.attributes["http.scheme"], "http")
        self.assertEqual(span.attributes["http.status_code"], 200)
        self.assertEqual(span.attributes["http.status_text"], "OK")

    @pytest.mark.skip(reason="TODO")
    async def test_error(self):
        with self.assertRaises(ValueError):
            await self.async_client.get("/error/")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]

        self.assertEqual(span.name, "^error/")
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes["http.method"], "GET")
        self.assertEqual(
            span.attributes["http.url"], "http://testserver/error/"
        )
        self.assertEqual(span.attributes["http.route"], "^error/")
        self.assertEqual(span.attributes["http.scheme"], "http")
        self.assertEqual(span.attributes["http.status_code"], 500)

        self.assertEqual(len(span.events), 1)
        event = span.events[0]
        self.assertEqual(event.name, "exception")
        self.assertEqual(event.attributes["exception.type"], "ValueError")
        self.assertEqual(event.attributes["exception.message"], "error")

    async def test_exclude_lists(self):
        await self.async_client.get("/excluded_arg/123")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

        await self.async_client.get("/excluded_arg/125")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        await self.async_client.get("/excluded_noarg/")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        await self.async_client.get("/excluded_noarg2/")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    async def test_span_name(self):
        # test no query_string
        await self.async_client.get("/span_name/1234/")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        span = span_list[0]
        self.assertEqual(span.name, "^span_name/([0-9]{4})/$")

    async def test_span_name_for_query_string(self):
        """
        request not have query string
        """
        await self.async_client.get("/span_name/1234/?query=test")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        span = span_list[0]
        self.assertEqual(span.name, "^span_name/([0-9]{4})/$")

    async def test_span_name_404(self):
        await self.async_client.get("/span_name/1234567890/")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        span = span_list[0]
        self.assertEqual(span.name, "HTTP GET")

    @pytest.mark.skip(reason="TODO")
    async def test_traced_request_attrs(self):
        await self.async_client.get("/span_name/1234/", CONTENT_TYPE="test/ct")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        span = span_list[0]
        self.assertEqual(span.attributes["path_info"], "/span_name/1234/")
        self.assertEqual(span.attributes["content_type"], "test/ct")
        self.assertNotIn("non_existing_variable", span.attributes)
