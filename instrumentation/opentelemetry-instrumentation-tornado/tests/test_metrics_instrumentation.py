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

from tornado.testing import AsyncHTTPTestCase

from opentelemetry import trace
from opentelemetry.instrumentation.tornado import TornadoInstrumentor
from opentelemetry.test.test_base import TestBase

from .tornado_test_app import make_app


class TornadoTest(AsyncHTTPTestCase, TestBase):
    # pylint:disable=no-self-use
    def get_app(self):
        tracer = trace.get_tracer(__name__)
        app = make_app(tracer)
        return app

    def setUp(self):
        super().setUp()
        TornadoInstrumentor().instrument(
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
            meter_provider=self.meter_provider,
        )

    def tearDown(self):
        TornadoInstrumentor().uninstrument()
        super().tearDown()


class TestTornadoInstrumentor(TornadoTest):
    def test_basic_metrics(self):
        start_time = default_timer()
        response = self.fetch("/")
        client_duration_estimated = (default_timer() - start_time) * 1000

        expected_attributes = {
            "http.status_code": 200,
            "http.method": "GET",
            "http.flavor": "HTTP/1.1",
            "http.scheme": "http",
            "http.host": response.request.headers["host"],
        }
        expected_response_attributes = {
            "http.status_code": response.code,
            "http.method": "GET",
            "http.url": self.get_url("/"),
        }
        expected_data = {
            "http.server.request.size": 0,
            "http.server.response.size": int(
                response.headers["Content-Length"]
            ),
        }
        expected_metrics = [
            "http.server.duration",
            "http.server.request.size",
            "http.server.response.size",
            "http.server.active_requests",
        ]

        resource_metrics = (
            self.memory_metrics_reader.get_metrics_data().resource_metrics
        )
        for metrics in resource_metrics:
            for scope_metrics in metrics.scope_metrics:
                self.assertEqual(
                    len(scope_metrics.metrics), len(expected_metrics)
                )
                for metric in scope_metrics.metrics:
                    for data_point in metric.data.data_points:
                        if metric.name in expected_data:
                            self.assertEqual(
                                data_point.sum, expected_data[metric.name]
                            )

                        self.assertIn(metric.name, expected_metrics)
                        if metric.name == "http.server.duration":
                            self.assertAlmostEqual(
                                data_point.sum,
                                client_duration_estimated,
                                delta=1000,
                            )

                        if metric.name == "http.server.response.size":
                            self.assertDictEqual(
                                expected_response_attributes,
                                dict(data_point.attributes),
                            )
                        else:
                            self.assertDictEqual(
                                expected_attributes,
                                dict(data_point.attributes),
                            )

    def test_metric_uninstrument(self):
        self.fetch("/")
        TornadoInstrumentor().uninstrument()
        self.fetch("/")

        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for resource_metric in metrics_list.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    if metric.name != "http.server.active_requests":
                        for point in list(metric.data.data_points):
                            self.assertEqual(point.count, 1)
