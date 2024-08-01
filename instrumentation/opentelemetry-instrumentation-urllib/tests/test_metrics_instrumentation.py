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


from platform import python_implementation
from timeit import default_timer
from unittest.mock import patch
from urllib import request
from urllib.parse import urlencode

import httpretty
from pytest import mark

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.urllib import (  # pylint: disable=no-name-in-module,import-error
    URLLibInstrumentor,
)
from opentelemetry.semconv._incubating.metrics.http_metrics import (
    HTTP_CLIENT_REQUEST_BODY_SIZE,
    HTTP_CLIENT_RESPONSE_BODY_SIZE,
)
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.semconv.metrics.http_metrics import (
    HTTP_CLIENT_REQUEST_DURATION,
)
from opentelemetry.test.test_base import TestBase


class TestUrllibMetricsInstrumentation(TestBase):
    URL = "http://mock/status/200"
    URL_POST = "http://mock/post"

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

        self.env_patch = patch.dict(
            "os.environ",
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()
        URLLibInstrumentor().instrument()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, self.URL, body=b"Hello!")
        httpretty.register_uri(
            httpretty.POST, self.URL_POST, body=b"Hello World!"
        )

    def tearDown(self):
        super().tearDown()
        URLLibInstrumentor().uninstrument()
        httpretty.disable()

    # Return Sequence with one histogram
    def create_histogram_data_points(self, sum_data_point, attributes):
        return [
            self.create_histogram_data_point(
                sum_data_point, 1, sum_data_point, sum_data_point, attributes
            )
        ]

    def test_basic_metric(self):
        start_time = default_timer()
        with request.urlopen(self.URL) as result:
            client_duration_estimated = (default_timer() - start_time) * 1000

            metrics = self.get_sorted_metrics()
            self.assertEqual(len(metrics), 3)

            (
                client_duration,
                client_request_size,
                client_response_size,
            ) = metrics[:3]

            self.assertEqual(
                client_duration.name, MetricInstruments.HTTP_CLIENT_DURATION
            )

            self.assert_metric_expected(
                client_duration,
                self.create_histogram_data_points(
                    client_duration_estimated,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "GET",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
                est_value_delta=40,
            )

            self.assertEqual(
                client_request_size.name,
                MetricInstruments.HTTP_CLIENT_REQUEST_SIZE,
            )
            self.assert_metric_expected(
                client_request_size,
                self.create_histogram_data_points(
                    0,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "GET",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
            )

            self.assertEqual(
                client_response_size.name,
                MetricInstruments.HTTP_CLIENT_RESPONSE_SIZE,
            )
            self.assert_metric_expected(
                client_response_size,
                self.create_histogram_data_points(
                    result.length,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "GET",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
            )

    def test_basic_metric_new_semconv(self):
        start_time = default_timer()
        with request.urlopen(self.URL) as result:
            duration_s = default_timer() - start_time

            metrics = self.get_sorted_metrics()
            self.assertEqual(len(metrics), 3)

            (
                client_request_body_size,
                client_request_duration,
                client_response_body_size,
            ) = metrics[:3]

            self.assertEqual(
                client_request_duration.name, HTTP_CLIENT_REQUEST_DURATION
            )

            self.assert_metric_expected(
                client_request_duration,
                self.create_histogram_data_points(
                    duration_s,
                    attributes={
                        "http.response.status_code": int(result.code),
                        "http.request.method": "GET",
                        "network.protocol.version": "1.1",
                    },
                ),
                est_value_delta=40,
            )

            self.assertEqual(
                client_request_body_size.name,
                HTTP_CLIENT_REQUEST_BODY_SIZE,
            )
            self.assert_metric_expected(
                client_request_body_size,
                self.create_histogram_data_points(
                    0,
                    attributes={
                        "http.response.status_code": int(result.code),
                        "http.request.method": "GET",
                        "network.protocol.version": "1.1",
                    },
                ),
            )

            self.assertEqual(
                client_response_body_size.name,
                HTTP_CLIENT_RESPONSE_BODY_SIZE,
            )
            self.assert_metric_expected(
                client_response_body_size,
                self.create_histogram_data_points(
                    result.length,
                    attributes={
                        "http.response.status_code": int(result.code),
                        "http.request.method": "GET",
                        "network.protocol.version": "1.1",
                    },
                ),
            )

    def test_basic_metric_both_semconv(self):
        start_time = default_timer()
        with request.urlopen(self.URL) as result:
            duration_s = default_timer() - start_time
            duration = max(round(duration_s * 1000), 0)

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

            self.assertEqual(
                client_duration.name, MetricInstruments.HTTP_CLIENT_DURATION
            )

            self.assert_metric_expected(
                client_duration,
                self.create_histogram_data_points(
                    duration,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "GET",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
                est_value_delta=40,
            )

            self.assertEqual(
                client_request_size.name,
                MetricInstruments.HTTP_CLIENT_REQUEST_SIZE,
            )
            self.assert_metric_expected(
                client_request_size,
                self.create_histogram_data_points(
                    0,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "GET",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
            )

            self.assertEqual(
                client_response_size.name,
                MetricInstruments.HTTP_CLIENT_RESPONSE_SIZE,
            )
            self.assert_metric_expected(
                client_response_size,
                self.create_histogram_data_points(
                    result.length,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "GET",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
            )

            self.assertEqual(
                client_request_duration.name, HTTP_CLIENT_REQUEST_DURATION
            )

            self.assert_metric_expected(
                client_request_duration,
                self.create_histogram_data_points(
                    duration_s,
                    attributes={
                        "http.response.status_code": int(result.code),
                        "http.request.method": "GET",
                        "network.protocol.version": "1.1",
                    },
                ),
                est_value_delta=40,
            )

            self.assertEqual(
                client_request_body_size.name,
                HTTP_CLIENT_REQUEST_BODY_SIZE,
            )
            self.assert_metric_expected(
                client_request_body_size,
                self.create_histogram_data_points(
                    0,
                    attributes={
                        "http.response.status_code": int(result.code),
                        "http.request.method": "GET",
                        "network.protocol.version": "1.1",
                    },
                ),
            )

            self.assertEqual(
                client_response_body_size.name,
                HTTP_CLIENT_RESPONSE_BODY_SIZE,
            )
            self.assert_metric_expected(
                client_response_body_size,
                self.create_histogram_data_points(
                    result.length,
                    attributes={
                        "http.response.status_code": int(result.code),
                        "http.request.method": "GET",
                        "network.protocol.version": "1.1",
                    },
                ),
            )

    def test_basic_metric_request_not_empty(self):
        data = {"header1": "value1", "header2": "value2"}
        data_encoded = urlencode(data).encode()

        start_time = default_timer()
        with request.urlopen(self.URL_POST, data=data_encoded) as result:
            client_duration_estimated = (default_timer() - start_time) * 1000

            metrics = self.get_sorted_metrics()
            self.assertEqual(len(metrics), 3)

            (
                client_duration,
                client_request_size,
                client_response_size,
            ) = metrics[:3]

            self.assertEqual(
                client_duration.name, MetricInstruments.HTTP_CLIENT_DURATION
            )
            self.assert_metric_expected(
                client_duration,
                self.create_histogram_data_points(
                    client_duration_estimated,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "POST",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
                est_value_delta=40,
            )

            self.assertEqual(
                client_request_size.name,
                MetricInstruments.HTTP_CLIENT_REQUEST_SIZE,
            )
            self.assert_metric_expected(
                client_request_size,
                self.create_histogram_data_points(
                    len(data_encoded),
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "POST",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
            )

            self.assertEqual(
                client_response_size.name,
                MetricInstruments.HTTP_CLIENT_RESPONSE_SIZE,
            )
            self.assert_metric_expected(
                client_response_size,
                self.create_histogram_data_points(
                    result.length,
                    attributes={
                        "http.status_code": int(result.code),
                        "http.method": "POST",
                        "http.url": str(result.url),
                        "http.flavor": "1.1",
                    },
                ),
            )

    @mark.skipif(
        python_implementation() == "PyPy", reason="Fails randomly in pypy"
    )
    def test_metric_uninstrument(self):
        with request.urlopen(self.URL):

            self.assertEqual(
                len(
                    (
                        self.memory_metrics_reader.get_metrics_data()
                        .resource_metrics[0]
                        .scope_metrics[0]
                        .metrics
                    )
                ),
                3,
            )

            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[0]
                    .data.data_points[0]
                    .bucket_counts[1]
                ),
                1,
            )
            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[1]
                    .data.data_points[0]
                    .bucket_counts[0]
                ),
                1,
            )
            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[2]
                    .data.data_points[0]
                    .bucket_counts[2]
                ),
                1,
            )

        with request.urlopen(self.URL):

            self.assertEqual(
                len(
                    (
                        self.memory_metrics_reader.get_metrics_data()
                        .resource_metrics[0]
                        .scope_metrics[0]
                        .metrics
                    )
                ),
                3,
            )

            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[0]
                    .data.data_points[0]
                    .bucket_counts[1]
                ),
                2,
            )
            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[1]
                    .data.data_points[0]
                    .bucket_counts[0]
                ),
                2,
            )
            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[2]
                    .data.data_points[0]
                    .bucket_counts[2]
                ),
                2,
            )

        URLLibInstrumentor().uninstrument()

        with request.urlopen(self.URL):

            self.assertEqual(
                len(
                    (
                        self.memory_metrics_reader.get_metrics_data()
                        .resource_metrics[0]
                        .scope_metrics[0]
                        .metrics
                    )
                ),
                3,
            )

            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[0]
                    .data.data_points[0]
                    .bucket_counts[1]
                ),
                2,
            )
            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[1]
                    .data.data_points[0]
                    .bucket_counts[0]
                ),
                2,
            )
            self.assertEqual(
                (
                    self.memory_metrics_reader.get_metrics_data()
                    .resource_metrics[0]
                    .scope_metrics[0]
                    .metrics[2]
                    .data.data_points[0]
                    .bucket_counts[2]
                ),
                2,
            )
