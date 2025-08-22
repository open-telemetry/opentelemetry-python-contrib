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
from unittest.mock import patch

import flask

from opentelemetry.instrumentation._labeler import (
    clear_labeler,
    get_labeler,
)
from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
)
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.test.wsgitestutil import WsgiTestBase

# pylint: disable=import-error
from .base_test import InstrumentationTest


_expected_metric_names_old = [
    "http.server.active_requests",
    "http.server.duration",
]
_expected_metric_names_new = [
    "http.server.active_requests",
    "http.server.request.duration",
]

_custom_attributes = [
    "custom_attr", "endpoint_type", "feature_flag"
]

_server_duration_attrs_old_with_custom = _server_duration_attrs_old.copy()
_server_duration_attrs_old_with_custom.append("http.target")
_server_duration_attrs_old_with_custom.extend(_custom_attributes)
_server_duration_attrs_new_with_custom = _server_duration_attrs_new.copy()
_server_duration_attrs_new_with_custom.append("http.route")
_server_duration_attrs_new_with_custom.extend(_custom_attributes)

_recommended_metrics_attrs_old_with_custom = {
    "http.server.active_requests": _server_active_requests_count_attrs_old,
    "http.server.duration": _server_duration_attrs_old_with_custom,
}
_recommended_metrics_attrs_new_with_custom = {
    "http.server.active_requests": _server_active_requests_count_attrs_new,
    "http.server.request.duration": _server_duration_attrs_new_with_custom,
}


class TestFlaskLabeler(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()

        test_name = ""
        if hasattr(self, "_testMethodName"):
            test_name = self._testMethodName
        sem_conv_mode = "default"
        if "new_semconv" in test_name:
            sem_conv_mode = "http"
        self.env_patch = patch.dict(
            "os.environ",
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()

        clear_labeler()
        self.app = flask.Flask(__name__)

        @self.app.route("/test_labeler")
        def test_labeler_route():
            labeler = get_labeler()
            labeler.add("custom_attr", "test_value")
            labeler.add_attributes({
                "endpoint_type": "test",
                "feature_flag": True
            })
            return "OK"
        
        @self.app.route("/no_labeler")
        def test_no_labeler_route():
            return "No labeler"

        FlaskInstrumentor().instrument_app(self.app)
        self._common_initialization()

    def tearDown(self):
        super().tearDown()
        clear_labeler()
        with self.disable_logging():
            FlaskInstrumentor().uninstrument_app(self.app)

    def test_flask_metrics_custom_attributes(self):
        start = default_timer()
        self.client.get("/test_labeler")
        self.client.get("/test_labeler")
        self.client.get("/test_labeler")
        duration = max(round((default_timer() - start) * 1000), 0)
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False
        self.assertTrue(len(metrics_list.resource_metrics) != 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) != 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertTrue(len(scope_metric.metrics) != 0)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names_old)
                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)
                    for point in data_points:
                        if isinstance(point, HistogramDataPoint):
                            self.assertEqual(point.count, 3)
                            self.assertAlmostEqual(
                                duration, point.sum, delta=10
                            )
                            histogram_data_point_seen = True
                        if isinstance(point, NumberDataPoint):
                            number_data_point_seen = True
                        for attr in point.attributes:
                            self.assertIn(
                                attr,
                                _recommended_metrics_attrs_old_with_custom[metric.name],
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_flask_metrics_custom_attributes_new_semconv(self):
        start = default_timer()
        self.client.get("/test_labeler")
        self.client.get("/test_labeler")
        self.client.get("/test_labeler")
        duration_s = max(default_timer() - start, 0)
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False
        self.assertTrue(len(metrics_list.resource_metrics) != 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) != 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertTrue(len(scope_metric.metrics) != 0)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names_new)
                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)
                    for point in data_points:
                        if isinstance(point, HistogramDataPoint):
                            self.assertEqual(point.count, 3)
                            self.assertAlmostEqual(
                                duration_s, point.sum, places=1
                            )
                            self.assertEqual(
                                point.explicit_bounds,
                                HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                            )
                            histogram_data_point_seen = True
                        if isinstance(point, NumberDataPoint):
                            number_data_point_seen = True
                        for attr in point.attributes:
                            self.assertIn(
                                attr,
                                _recommended_metrics_attrs_new_with_custom[metric.name],
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)