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

import tornado.testing

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
