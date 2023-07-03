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

import httpretty
import urllib3
import urllib3.exceptions
from urllib3 import encode_multipart_formdata

from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.test.httptest import HttpTestBase
from opentelemetry.test.test_base import TestBase


class TestURLLib3InstrumentorMetric(HttpTestBase, TestBase):
    HTTP_URL = "http://mock/status/200"

    def setUp(self):
        super().setUp()
        URLLib3Instrumentor().instrument()
        httpretty.enable(allow_net_connect=False)
        httpretty.register_uri(httpretty.GET, self.HTTP_URL, body="Hello!")
        httpretty.register_uri(httpretty.POST, self.HTTP_URL, body="Hello!")
        self.pool = urllib3.PoolManager()

    def tearDown(self):
        super().tearDown()
        self.pool.clear()
        URLLib3Instrumentor().uninstrument()

        httpretty.disable()
        httpretty.reset()

    def test_basic_metrics(self):
        start_time = default_timer()
        response = self.pool.request("GET", self.HTTP_URL)
        client_duration_estimated = (default_timer() - start_time) * 1000

        metrics = self.get_sorted_metrics()

        (
            client_duration,
            client_request_size,
            client_response_size,
        ) = metrics

        self.assertEqual(client_duration.name, "http.client.duration")
        self.assert_metric_expected(
            client_duration,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=client_duration_estimated,
                    max_data_point=client_duration_estimated,
                    min_data_point=client_duration_estimated,
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "GET",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
                )
            ],
            est_value_delta=200,
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
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "GET",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
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
                    attributes={
                        "http.flavor": "1.1",
                        "http.host": "mock",
                        "http.method": "GET",
                        "http.scheme": "http",
                        "http.status_code": 200,
                        "net.peer.name": "mock",
                        "net.peer.port": 80,
                    },
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
