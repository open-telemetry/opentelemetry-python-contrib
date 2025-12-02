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


import asyncio
from timeit import default_timer
from unittest.mock import patch

import tornado.testing
from tornado.testing import AsyncHTTPTestCase

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.tornado import TornadoInstrumentor
from opentelemetry.sdk.metrics.export import HistogramDataPoint
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_HOST,
    HTTP_METHOD,
    HTTP_SCHEME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_URL,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_FULL,
    URL_PATH,
    URL_SCHEME,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

from .test_instrumentation import (  # pylint: disable=no-name-in-module,import-error
    TornadoTest,
)
from .tornado_test_app import make_app


class TestTornadoMetricsInstrumentation(TornadoTest):
    # Return Sequence with one histogram
    def create_histogram_data_points(self, sum_data_point, attributes):
        return [
            self.create_histogram_data_point(
                sum_data_point, 1, sum_data_point, sum_data_point, attributes
            )
        ]

    def test_basic_metrics(self):
        start_time = default_timer()
        response = self.fetch("/")
        client_duration_estimated = (default_timer() - start_time) * 1000

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 7)

        (
            client_duration,
            client_request_size,
            client_response_size,
        ) = metrics[:3]

        (
            server_active_request,
            server_duration,
            server_request_size,
            server_response_size,
        ) = metrics[3:]

        self.assertEqual(
            server_active_request.name, "http.server.active_requests"
        )
        self.assert_metric_expected(
            server_active_request,
            [
                self.create_number_data_point(
                    0,
                    attributes={
                        "http.method": "GET",
                        "http.flavor": "HTTP/1.1",
                        "http.scheme": "http",
                        "http.target": "/",
                        "http.host": response.request.headers["host"],
                    },
                ),
            ],
        )

        self.assertEqual(server_duration.name, "http.server.duration")
        self.assert_metric_expected(
            server_duration,
            self.create_histogram_data_points(
                client_duration_estimated,
                attributes={
                    "http.method": "GET",
                    "http.flavor": "HTTP/1.1",
                    "http.scheme": "http",
                    "http.target": "/",
                    "http.host": response.request.headers["host"],
                    "http.status_code": response.code,
                },
            ),
            est_value_delta=200,
        )

        self.assertEqual(server_request_size.name, "http.server.request.size")
        self.assert_metric_expected(
            server_request_size,
            self.create_histogram_data_points(
                0,
                attributes={
                    "http.status_code": 200,
                    "http.method": "GET",
                    "http.flavor": "HTTP/1.1",
                    "http.scheme": "http",
                    "http.target": "/",
                    "http.host": response.request.headers["host"],
                },
            ),
        )

        self.assertEqual(
            server_response_size.name, "http.server.response.size"
        )
        self.assert_metric_expected(
            server_response_size,
            self.create_histogram_data_points(
                len(response.body),
                attributes={
                    "http.status_code": response.code,
                    "http.method": "GET",
                    "http.flavor": "HTTP/1.1",
                    "http.scheme": "http",
                    "http.target": "/",
                    "http.host": response.request.headers["host"],
                },
            ),
        )

        self.assertEqual(client_duration.name, "http.client.duration")
        self.assert_metric_expected(
            client_duration,
            self.create_histogram_data_points(
                client_duration_estimated,
                attributes={
                    "http.status_code": response.code,
                    "http.method": "GET",
                    "http.url": response.effective_url,
                },
            ),
            est_value_delta=200,
        )

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            self.create_histogram_data_points(
                0,
                attributes={
                    "http.status_code": response.code,
                    "http.method": "GET",
                    "http.url": response.effective_url,
                },
            ),
        )

        self.assertEqual(
            client_response_size.name, "http.client.response.size"
        )
        self.assert_metric_expected(
            client_response_size,
            self.create_histogram_data_points(
                len(response.body),
                attributes={
                    "http.status_code": response.code,
                    "http.method": "GET",
                    "http.url": response.effective_url,
                },
            ),
        )

    @tornado.testing.gen_test
    async def test_metrics_concurrent_requests(self):
        """
        Test that metrics can handle concurrent requests and calculate in an async-safe way.
        """
        req1 = self.http_client.fetch(self.get_url("/slow?duration=1.0"))
        req2 = self.http_client.fetch(self.get_url("/async"))
        await asyncio.gather(req1, req2)

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 7)

        client_duration = metrics[0]
        server_duration = metrics[4]
        self.assertEqual(client_duration.name, "http.client.duration")
        self.assertEqual(server_duration.name, "http.server.duration")

        # Calculating duration requires tracking state via `_HANDLER_STATE_KEY`, so we want to make sure
        # duration is calculated properly per request, and doesn't affect concurrent requests.
        req1_client_duration_data_point = next(
            dp
            for dp in client_duration.data.data_points
            if "/slow" in dp.attributes.get("http.url")
        )
        req1_server_duration_data_point = next(
            dp
            for dp in server_duration.data.data_points
            if "/slow" in dp.attributes.get("http.target")
        )
        req2_client_duration_data_point = next(
            dp
            for dp in client_duration.data.data_points
            if "/async" in dp.attributes.get("http.url")
        )
        req2_server_duration_data_point = next(
            dp
            for dp in server_duration.data.data_points
            if "/async" in dp.attributes.get("http.target")
        )

        # Server and client durations should be similar (adjusting for msecs vs secs)
        self.assertAlmostEqual(
            abs(
                req1_server_duration_data_point.sum / 1000.0
                - req1_client_duration_data_point.sum
            ),
            0.0,
            delta=0.01,
        )
        self.assertAlmostEqual(
            abs(
                req2_server_duration_data_point.sum / 1000.0
                - req2_client_duration_data_point.sum
            ),
            0.0,
            delta=0.01,
        )

        # Make sure duration is roughly equivalent to expected (req1/slow) should be around 1 second
        self.assertAlmostEqual(
            req1_server_duration_data_point.sum / 1000.0,
            1.0,
            delta=0.1,
            msg="Should have been about 1 second",
        )
        self.assertAlmostEqual(
            req2_server_duration_data_point.sum / 1000.0,
            0.0,
            delta=0.1,
            msg="Should have been really short",
        )

    def test_metric_uninstrument(self):
        self.fetch("/")
        TornadoInstrumentor().uninstrument()
        self.fetch("/")

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 7)

        for metric in metrics:
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)

    def test_exclude_lists(self):
        def test_excluded(path):
            self.fetch(path)

            # Verify no server metrics written (only client ones should exist)
            metrics = self.get_sorted_metrics()
            for metric in metrics:
                self.assertTrue("http.server" not in metric.name, metric)
            self.assertEqual(len(metrics), 3, metrics)

        test_excluded("/healthz")
        test_excluded("/ping")


class TornadoSemconvTestBase(AsyncHTTPTestCase, TestBase):
    def get_app(self):
        tracer = trace.get_tracer(__name__)
        app = make_app(tracer)
        return app

    def setUp(self):
        super().setUp()

    def tearDown(self):
        TornadoInstrumentor().uninstrument()
        super().tearDown()

    def _get_server_span(self, spans):
        for span in spans:
            if span.kind == SpanKind.SERVER:
                return span
        return None

    def _get_client_span(self, spans):
        for span in spans:
            if span.kind == SpanKind.CLIENT:
                return span
        return None


class TestTornadoSemconvDefault(TornadoSemconvTestBase):
    def setUp(self):
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False
        TornadoInstrumentor().instrument()

    def test_server_span_attributes_old_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        server_span = self._get_server_span(spans)
        self.assertIsNotNone(server_span)

        # Verify old semconv attributes are present
        self.assertIn(HTTP_METHOD, server_span.attributes)
        self.assertIn(HTTP_SCHEME, server_span.attributes)
        self.assertIn(HTTP_HOST, server_span.attributes)
        self.assertIn(HTTP_TARGET, server_span.attributes)
        self.assertIn(HTTP_STATUS_CODE, server_span.attributes)
        # Verify new semconv attributes are NOT present
        self.assertNotIn(HTTP_REQUEST_METHOD, server_span.attributes)
        self.assertNotIn(URL_SCHEME, server_span.attributes)
        self.assertNotIn(URL_PATH, server_span.attributes)
        self.assertNotIn(HTTP_RESPONSE_STATUS_CODE, server_span.attributes)
        # Verify schema URL
        self.assertEqual(
            server_span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.11.0",
        )

    def test_client_span_attributes_old_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        client_span = self._get_client_span(spans)
        self.assertIsNotNone(client_span)

        # Verify old semconv attributes are present
        self.assertIn(HTTP_METHOD, client_span.attributes)
        self.assertIn(HTTP_URL, client_span.attributes)
        self.assertIn(HTTP_STATUS_CODE, client_span.attributes)
        # Verify new semconv attributes are NOT present
        self.assertNotIn(HTTP_REQUEST_METHOD, client_span.attributes)
        self.assertNotIn(URL_FULL, client_span.attributes)
        self.assertNotIn(HTTP_RESPONSE_STATUS_CODE, client_span.attributes)

    def test_server_metrics_old_semconv(self):
        """Test that server metrics use old semantic conventions by default."""
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        metrics = self.memory_metrics_reader.get_metrics_data()
        resource_metrics = metrics.resource_metrics

        # Find old semconv metrics
        old_duration_found = False
        new_duration_found = False
        for rm in resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "http.server.duration":
                        old_duration_found = True
                        # Verify unit is milliseconds for old semconv
                        self.assertEqual(metric.unit, "ms")
                    elif metric.name == "http.server.request.duration":
                        new_duration_found = True
        self.assertTrue(old_duration_found, "Old semconv metric not found")
        self.assertFalse(
            new_duration_found, "New semconv metric should not be present"
        )


class TestTornadoSemconvHttpNew(TornadoSemconvTestBase):
    def setUp(self):
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False
        with patch.dict("os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http"}):
            TornadoInstrumentor().instrument()

    def test_server_span_attributes_new_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        server_span = self._get_server_span(spans)
        self.assertIsNotNone(server_span)

        # Verify new semconv attributes are present
        self.assertIn(HTTP_REQUEST_METHOD, server_span.attributes)
        self.assertIn(URL_SCHEME, server_span.attributes)
        self.assertIn(HTTP_RESPONSE_STATUS_CODE, server_span.attributes)
        # Verify old semconv attributes are NOT present
        self.assertNotIn(HTTP_METHOD, server_span.attributes)
        self.assertNotIn(HTTP_SCHEME, server_span.attributes)
        self.assertNotIn(HTTP_TARGET, server_span.attributes)
        self.assertNotIn(HTTP_STATUS_CODE, server_span.attributes)
        # Verify schema URL
        self.assertEqual(
            server_span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.21.0",
        )

    def test_client_span_attributes_new_semconv(self):
        """Test that client spans use new semantic conventions in http mode."""
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        client_span = self._get_client_span(spans)
        self.assertIsNotNone(client_span)

        # Verify new semconv attributes are present
        self.assertIn(HTTP_REQUEST_METHOD, client_span.attributes)
        self.assertIn(URL_FULL, client_span.attributes)
        self.assertIn(HTTP_RESPONSE_STATUS_CODE, client_span.attributes)
        # Verify old semconv attributes are NOT present
        self.assertNotIn(HTTP_METHOD, client_span.attributes)
        self.assertNotIn(HTTP_URL, client_span.attributes)
        self.assertNotIn(HTTP_STATUS_CODE, client_span.attributes)

    def test_server_metrics_new_semconv(self):
        """Test that server metrics use new semantic conventions in http mode."""
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        metrics = self.memory_metrics_reader.get_metrics_data()
        resource_metrics = metrics.resource_metrics

        # Find new semconv metrics
        old_duration_found = False
        new_duration_found = False
        for rm in resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "http.server.duration":
                        old_duration_found = True
                    elif metric.name == "http.server.request.duration":
                        new_duration_found = True
                        # Verify unit is seconds for new semconv
                        self.assertEqual(metric.unit, "s")
        self.assertFalse(
            old_duration_found, "Old semconv metric should not be present"
        )
        self.assertTrue(new_duration_found, "New semconv metric not found")


class TestTornadoSemconvHttpDup(TornadoSemconvTestBase):
    def setUp(self):
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False
        with patch.dict(
            "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http/dup"}
        ):
            TornadoInstrumentor().instrument()

    def test_server_span_attributes_both_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        server_span = self._get_server_span(spans)
        self.assertIsNotNone(server_span)

        # Verify old semconv attributes are present
        self.assertIn(HTTP_METHOD, server_span.attributes)
        self.assertIn(HTTP_SCHEME, server_span.attributes)
        self.assertIn(HTTP_HOST, server_span.attributes)
        self.assertIn(HTTP_TARGET, server_span.attributes)
        self.assertIn(HTTP_STATUS_CODE, server_span.attributes)
        # Verify new semconv attributes are also present
        self.assertIn(HTTP_REQUEST_METHOD, server_span.attributes)
        self.assertIn(URL_SCHEME, server_span.attributes)
        self.assertIn(HTTP_RESPONSE_STATUS_CODE, server_span.attributes)
        # Verify values match between old and new
        self.assertEqual(
            server_span.attributes[HTTP_METHOD],
            server_span.attributes[HTTP_REQUEST_METHOD],
        )
        self.assertEqual(
            server_span.attributes[HTTP_STATUS_CODE],
            server_span.attributes[HTTP_RESPONSE_STATUS_CODE],
        )
        self.assertEqual(
            server_span.attributes[HTTP_SCHEME],
            server_span.attributes[URL_SCHEME],
        )
        # Verify schema URL (in dup mode, schema_url should be the new one)
        self.assertEqual(
            server_span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.21.0",
        )

    def test_client_span_attributes_both_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        client_span = self._get_client_span(spans)
        self.assertIsNotNone(client_span)

        # Verify old semconv attributes are present
        self.assertIn(HTTP_METHOD, client_span.attributes)
        self.assertIn(HTTP_URL, client_span.attributes)
        self.assertIn(HTTP_STATUS_CODE, client_span.attributes)
        # Verify new semconv attributes are also present
        self.assertIn(HTTP_REQUEST_METHOD, client_span.attributes)
        self.assertIn(URL_FULL, client_span.attributes)
        self.assertIn(HTTP_RESPONSE_STATUS_CODE, client_span.attributes)
        # Verify values match between old and new
        self.assertEqual(
            client_span.attributes[HTTP_METHOD],
            client_span.attributes[HTTP_REQUEST_METHOD],
        )
        self.assertEqual(
            client_span.attributes[HTTP_STATUS_CODE],
            client_span.attributes[HTTP_RESPONSE_STATUS_CODE],
        )

    def test_server_metrics_both_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        metrics = self.memory_metrics_reader.get_metrics_data()
        resource_metrics = metrics.resource_metrics

        # Find both old and new semconv metrics
        old_duration_found = False
        new_duration_found = False
        for rm in resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "http.server.duration":
                        old_duration_found = True
                        self.assertEqual(metric.unit, "ms")
                    elif metric.name == "http.server.request.duration":
                        new_duration_found = True
                        self.assertEqual(metric.unit, "s")
        self.assertTrue(old_duration_found, "Old semconv metric not found")
        self.assertTrue(new_duration_found, "New semconv metric not found")

    def test_client_metrics_both_semconv(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        metrics = self.memory_metrics_reader.get_metrics_data()
        resource_metrics = metrics.resource_metrics

        # Find both old and new semconv metrics
        old_duration_found = False
        new_duration_found = False
        for rm in resource_metrics:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    if metric.name == "http.client.duration":
                        old_duration_found = True
                        self.assertEqual(metric.unit, "ms")
                    elif metric.name == "http.client.request.duration":
                        new_duration_found = True
                        self.assertEqual(metric.unit, "s")
        self.assertTrue(
            old_duration_found, "Old semconv client metric not found"
        )
        self.assertTrue(
            new_duration_found, "New semconv client metric not found"
        )
