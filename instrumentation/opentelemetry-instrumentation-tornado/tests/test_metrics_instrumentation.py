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

from opentelemetry.instrumentation.tornado import TornadoInstrumentor
from opentelemetry.sdk.metrics.export import HistogramDataPoint

from .test_instrumentation import (  # pylint: disable=no-name-in-module,import-error
    TornadoTest,
)


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
