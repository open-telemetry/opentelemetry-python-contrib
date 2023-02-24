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

from timeit import default_timer

import urllib3
import urllib3.exceptions
from urllib3.request import encode_multipart_formdata

from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.test.httptest import HttpTestBase
from opentelemetry.test.test_base import TestBase


class TestUrllib3MetricsInstrumentation(HttpTestBase, TestBase):
    def setUp(self):
        super().setUp()
        self.assert_ip = self.server.server_address[0]
        self.assert_port = self.server.server_address[1]
        self.http_host = ":".join(map(str, self.server.server_address[:2]))
        self.http_url_base = "http://" + self.http_host
        self.http_url = self.http_url_base + "/status/200"
        URLLib3Instrumentor().instrument(meter_provider=self.meter_provider)

    def tearDown(self):
        super().tearDown()
        URLLib3Instrumentor().uninstrument()

    # Return Sequence with one histogram
    def create_histogram_data_points(self, sum_data_point, attributes):
        return [
            self.create_histogram_data_point(
                sum_data_point, 1, sum_data_point, sum_data_point, attributes
            )
        ]

    def test_basic_metric_check_client_size_get(self):
        with urllib3.PoolManager() as pool:
            start_time = default_timer()
            response = pool.request("GET", self.http_url)
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
                self.create_histogram_data_points(
                    client_duration_estimated,
                    attributes={
                        "http.status_code": 200,
                        "http.host": self.assert_ip,
                        "http.method": "GET",
                        "http.flavor": "1.1",
                        "http.scheme": "http",
                        "net.peer.name": self.assert_ip,
                        "net.peer.port": self.assert_port,
                    },
                ),
                est_value_delta=200,
            )

            self.assertEqual(
                client_request_size.name, "http.client.request.size"
            )
            self.assert_metric_expected(
                client_request_size,
                self.create_histogram_data_points(
                    0,
                    attributes={
                        "http.status_code": 200,
                        "http.host": self.assert_ip,
                        "http.method": "GET",
                        "http.flavor": "1.1",
                        "http.scheme": "http",
                        "net.peer.name": self.assert_ip,
                        "net.peer.port": self.assert_port,
                    },
                ),
            )

            self.assertEqual(
                client_response_size.name, "http.client.response.size"
            )
            self.assert_metric_expected(
                client_response_size,
                self.create_histogram_data_points(
                    len(response.data),
                    attributes={
                        "http.status_code": 200,
                        "http.host": self.assert_ip,
                        "http.method": "GET",
                        "http.flavor": "1.1",
                        "http.scheme": "http",
                        "net.peer.name": self.assert_ip,
                        "net.peer.port": self.assert_port,
                    },
                ),
            )

    def test_basic_metric_check_client_size_post(self):
        with urllib3.PoolManager() as pool:
            start_time = default_timer()
            data_fields = {"data": "test"}
            response = pool.request("POST", self.http_url, fields=data_fields)
            client_duration_estimated = (default_timer() - start_time) * 1000
            body = encode_multipart_formdata(data_fields)[0]

            metrics = self.get_sorted_metrics()

            (
                client_duration,
                client_request_size,
                client_response_size,
            ) = metrics

            self.assertEqual(client_duration.name, "http.client.duration")
            self.assert_metric_expected(
                client_duration,
                self.create_histogram_data_points(
                    client_duration_estimated,
                    attributes={
                        "http.status_code": 501,
                        "http.host": self.assert_ip,
                        "http.method": "POST",
                        "http.flavor": "1.1",
                        "http.scheme": "http",
                        "net.peer.name": self.assert_ip,
                        "net.peer.port": self.assert_port,
                    },
                ),
                est_value_delta=200,
            )

            self.assertEqual(
                client_request_size.name, "http.client.request.size"
            )
            client_request_size_expected = len(body)
            self.assert_metric_expected(
                client_request_size,
                self.create_histogram_data_points(
                    client_request_size_expected,
                    attributes={
                        "http.status_code": 501,
                        "http.host": self.assert_ip,
                        "http.method": "POST",
                        "http.flavor": "1.1",
                        "http.scheme": "http",
                        "net.peer.name": self.assert_ip,
                        "net.peer.port": self.assert_port,
                    },
                ),
            )

            self.assertEqual(
                client_response_size.name, "http.client.response.size"
            )
            client_response_size_expected = len(response.data)
            self.assert_metric_expected(
                client_response_size,
                self.create_histogram_data_points(
                    client_response_size_expected,
                    attributes={
                        "http.status_code": 501,
                        "http.host": self.assert_ip,
                        "http.method": "POST",
                        "http.flavor": "1.1",
                        "http.scheme": "http",
                        "net.peer.name": self.assert_ip,
                        "net.peer.port": self.assert_port,
                    },
                ),
            )

    def test_metric_uninstrument(self):
        with urllib3.PoolManager() as pool:
            pool.request("GET", self.http_url)
            URLLib3Instrumentor().uninstrument()
            pool.request("GET", self.http_url)

            metrics = self.get_sorted_metrics()
            self.assertEqual(len(metrics), 3)

            for metric in metrics:
                for point in list(metric.data.data_points):
                    self.assertEqual(point.count, 1)
