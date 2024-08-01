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

import io
from timeit import default_timer
from unittest import mock

import httpretty
import urllib3
import urllib3.exceptions
from urllib3 import encode_multipart_formdata

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.test.httptest import HttpTestBase
from opentelemetry.test.test_base import TestBase


class TestURLLib3InstrumentorMetric(HttpTestBase, TestBase):
    HTTP_URL = "http://mock/status/200"

    def setUp(self):
        super().setUp()

        test_name = ""
        if hasattr(self, "_testMethodName"):
            test_name = self._testMethodName
        sem_conv_mode = "default"
        if "new_semconv" in test_name:
            sem_conv_mode = "http"
        elif "both_semconv" in test_name:
            sem_conv_mode = "http/dup"

        self.env_patch = mock.patch.dict(
            "os.environ",
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()
        URLLib3Instrumentor().instrument()
        httpretty.enable(allow_net_connect=False)
        httpretty.register_uri(httpretty.GET, self.HTTP_URL, body="Hello!")
        httpretty.register_uri(httpretty.POST, self.HTTP_URL, body="Hello!")
        self.pool = urllib3.PoolManager()

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        self.pool.clear()
        URLLib3Instrumentor().uninstrument()

        httpretty.disable()
        httpretty.reset()

    def test_basic_metrics(self):
        start_time = default_timer()
        response = self.pool.request("GET", self.HTTP_URL)
        duration_ms = max(round((default_timer() - start_time) * 1000), 0)
        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 3)

        (
            client_duration,
            client_request_size,
            client_response_size,
        ) = metrics

        attrs_old = {
            "http.status_code": 200,
            "http.host": "mock",
            "net.peer.port": 80,
            "net.peer.name": "mock",
            "http.method": "GET",
            "http.flavor": "1.1",
            "http.scheme": "http",
        }

        self.assertEqual(client_duration.name, "http.client.duration")
        self.assert_metric_expected(
            client_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=duration_ms,
                    max_data_point=duration_ms,
                    min_data_point=duration_ms,
                    attributes=attrs_old,
                )
            ],
            est_value_delta=40,
        )

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes=attrs_old,
                )
            ],
        )

        expected_size = len(response.data)
        self.assertEqual(
            client_response_size.name, "http.client.response.size"
        )
        self.assert_metric_expected(
            client_response_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_size,
                    max_data_point=expected_size,
                    min_data_point=expected_size,
                    attributes=attrs_old,
                )
            ],
        )

    def test_basic_metrics_new_semconv(self):
        start_time = default_timer()
        response = self.pool.request("GET", self.HTTP_URL)
        duration_s = max(default_timer() - start_time, 0)

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 3)
        (
            client_request_size,
            client_duration,
            client_response_size,
        ) = metrics

        attrs_new = {
            "network.protocol.version": "1.1",
            "server.address": "mock",
            "server.port": 80,
            "http.request.method": "GET",
            "http.response.status_code": 200,
            # TODO: add URL_SCHEME to tests when supported in the implementation
        }

        self.assertEqual(client_duration.name, "http.client.request.duration")
        self.assert_metric_expected(
            client_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=duration_s,
                    max_data_point=duration_s,
                    min_data_point=duration_s,
                    attributes=attrs_new,
                )
            ],
            est_value_delta=40 / 1000,
        )

        self.assertEqual(
            client_request_size.name, "http.client.request.body.size"
        )
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes=attrs_new,
                )
            ],
        )

        expected_size = len(response.data)
        self.assertEqual(
            client_response_size.name, "http.client.response.body.size"
        )
        self.assert_metric_expected(
            client_response_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_size,
                    max_data_point=expected_size,
                    min_data_point=expected_size,
                    attributes=attrs_new,
                )
            ],
        )

    def test_basic_metrics_both_semconv(self):
        start_time = default_timer()
        response = self.pool.request("GET", self.HTTP_URL)
        duration_s = max(default_timer() - start_time, 0)
        duration = max(round(duration_s * 1000), 0)
        expected_size = len(response.data)

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 6)

        (
            client_duration,
            client_request_body_size,
            client_request_duration,
            client_request_size,
            client_response_body_size,
            client_response_size,
        ) = metrics[:6]

        attrs_new = {
            "network.protocol.version": "1.1",
            "server.address": "mock",
            "server.port": 80,
            "http.request.method": "GET",
            "http.response.status_code": 200,
            # TODO: add URL_SCHEME to tests when supported in the implementation
        }

        attrs_old = {
            "http.status_code": 200,
            "http.host": "mock",
            "net.peer.port": 80,
            "net.peer.name": "mock",
            "http.method": "GET",
            "http.flavor": "1.1",
            "http.scheme": "http",
        }

        # assert new semconv metrics
        self.assertEqual(
            client_request_duration.name, "http.client.request.duration"
        )
        self.assert_metric_expected(
            client_request_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=duration_s,
                    max_data_point=duration_s,
                    min_data_point=duration_s,
                    attributes=attrs_new,
                )
            ],
            est_value_delta=40 / 1000,
        )

        self.assertEqual(
            client_request_body_size.name, "http.client.request.body.size"
        )
        self.assert_metric_expected(
            client_request_body_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes=attrs_new,
                )
            ],
        )

        self.assertEqual(
            client_response_body_size.name, "http.client.response.body.size"
        )
        self.assert_metric_expected(
            client_response_body_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_size,
                    max_data_point=expected_size,
                    min_data_point=expected_size,
                    attributes=attrs_new,
                )
            ],
        )
        # assert old semconv metrics
        self.assertEqual(client_duration.name, "http.client.duration")
        self.assert_metric_expected(
            client_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=duration,
                    max_data_point=duration,
                    min_data_point=duration,
                    attributes=attrs_old,
                )
            ],
            est_value_delta=40,
        )

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes=attrs_old,
                )
            ],
        )

        self.assertEqual(
            client_response_size.name, "http.client.response.size"
        )
        self.assert_metric_expected(
            client_response_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_size,
                    max_data_point=expected_size,
                    min_data_point=expected_size,
                    attributes=attrs_old,
                )
            ],
        )

    @mock.patch("httpretty.http.HttpBaseClass.METHODS", ("NONSTANDARD",))
    def test_basic_metrics_nonstandard_http_method(self):
        httpretty.register_uri(
            "NONSTANDARD", self.HTTP_URL, body="", status=405
        )

        start_time = default_timer()
        response = self.pool.request("NONSTANDARD", self.HTTP_URL)
        duration_ms = max(round((default_timer() - start_time) * 1000), 0)

        metrics = self.get_sorted_metrics()

        (
            client_duration,
            client_request_size,
            client_response_size,
        ) = metrics

        attrs_old = {
            "http.status_code": 405,
            "http.host": "mock",
            "net.peer.port": 80,
            "net.peer.name": "mock",
            "http.method": "_OTHER",
            "http.flavor": "1.1",
            "http.scheme": "http",
        }

        self.assertEqual(client_duration.name, "http.client.duration")
        self.assert_metric_expected(
            client_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=duration_ms,
                    max_data_point=duration_ms,
                    min_data_point=duration_ms,
                    attributes=attrs_old,
                )
            ],
            est_value_delta=40,
        )

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes=attrs_old,
                )
            ],
        )

        expected_size = len(response.data)
        self.assertEqual(
            client_response_size.name, "http.client.response.size"
        )
        self.assert_metric_expected(
            client_response_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_size,
                    max_data_point=expected_size,
                    min_data_point=expected_size,
                    attributes=attrs_old,
                )
            ],
        )

    @mock.patch("httpretty.http.HttpBaseClass.METHODS", ("NONSTANDARD",))
    def test_basic_metrics_nonstandard_http_method_new_semconv(self):
        httpretty.register_uri(
            "NONSTANDARD", self.HTTP_URL, body="", status=405
        )
        start_time = default_timer()
        response = self.pool.request("NONSTANDARD", self.HTTP_URL)
        duration_s = max(default_timer() - start_time, 0)

        metrics = self.get_sorted_metrics()

        (
            client_request_size,
            client_duration,
            client_response_size,
        ) = metrics

        attrs_new = {
            "network.protocol.version": "1.1",
            "server.address": "mock",
            "server.port": 80,
            "http.request.method": "_OTHER",
            "http.response.status_code": 405,
            "error.type": "405",
            # TODO: add URL_SCHEME to tests when supported in the implementation
        }

        self.assertEqual(client_duration.name, "http.client.request.duration")
        self.assert_metric_expected(
            client_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=duration_s,
                    max_data_point=duration_s,
                    min_data_point=duration_s,
                    attributes=attrs_new,
                )
            ],
            est_value_delta=40 / 1000,
        )

        self.assertEqual(
            client_request_size.name, "http.client.request.body.size"
        )
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes=attrs_new,
                )
            ],
        )

        expected_size = len(response.data)
        self.assertEqual(
            client_response_size.name, "http.client.response.body.size"
        )
        self.assert_metric_expected(
            client_response_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_size,
                    max_data_point=expected_size,
                    min_data_point=expected_size,
                    attributes=attrs_new,
                )
            ],
        )

    def test_str_request_body_size_metrics(self):
        self.pool.request("POST", self.HTTP_URL, body="foobar")

        metrics = self.get_sorted_metrics()
        (_, client_request_size, _) = metrics

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=6,
                    max_data_point=6,
                    min_data_point=6,
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "POST",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
                )
            ],
        )

    def test_schema_url(self):
        self.pool.request("POST", self.HTTP_URL, body="foobar")

        resource_metrics = (
            self.memory_metrics_reader.get_metrics_data().resource_metrics
        )

        for metrics in resource_metrics:
            for scope_metrics in metrics.scope_metrics:
                self.assertEqual(
                    scope_metrics.scope.schema_url,
                    "https://opentelemetry.io/schemas/1.11.0",
                )

    def test_bytes_request_body_size_metrics(self):
        self.pool.request("POST", self.HTTP_URL, body=b"foobar")

        metrics = self.get_sorted_metrics()
        (_, client_request_size, _) = metrics

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=6,
                    max_data_point=6,
                    min_data_point=6,
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "POST",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
                )
            ],
        )

    def test_fields_request_body_size_metrics(self):
        self.pool.request("POST", self.HTTP_URL, fields={"foo": "bar"})

        metrics = self.get_sorted_metrics()
        (_, client_request_size, _) = metrics

        self.assertEqual(client_request_size.name, "http.client.request.size")
        expected_value = len(encode_multipart_formdata({"foo": "bar"})[0])
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_value,
                    max_data_point=expected_value,
                    min_data_point=expected_value,
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "POST",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
                )
            ],
        )

    def test_bytesio_request_body_size_metrics(self):
        self.pool.request("POST", self.HTTP_URL, body=io.BytesIO(b"foobar"))

        metrics = self.get_sorted_metrics()
        (_, client_request_size, _) = metrics

        self.assertEqual(client_request_size.name, "http.client.request.size")
        self.assert_metric_expected(
            client_request_size,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=6,
                    max_data_point=6,
                    min_data_point=6,
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "POST",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
                )
            ],
        )

    def test_generator_request_body_size_metrics(self):
        self.pool.request(
            "POST", self.HTTP_URL, body=(b for b in (b"foo", b"bar"))
        )

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 2)
        self.assertNotIn("http.client.request.size", [m.name for m in metrics])

    def test_metric_uninstrument(self):
        self.pool.request("GET", self.HTTP_URL)
        URLLib3Instrumentor().uninstrument()
        self.pool.request("GET", self.HTTP_URL)

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 3)

        for metric in metrics:
            for point in list(metric.data.data_points):
                self.assertEqual(point.count, 1)
        # instrument again to avoid warning message on tearDown
        URLLib3Instrumentor().instrument()
