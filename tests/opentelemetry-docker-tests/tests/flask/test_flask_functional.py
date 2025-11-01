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

from flask import Flask

from opentelemetry import metrics as metrics_api
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.metrics import AlwaysOnExemplarFilter
from opentelemetry.test.globals_test import (
    reset_metrics_globals,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import (
    INVALID_SPAN_ID,
    INVALID_TRACE_ID,
)

class TestFunctionalFlask(TestBase):
    def setUp(self):
        super().setUp()
        self.memory_exporter.clear()
        # This is done because set_meter_provider cannot override the
        # current meter provider.
        reset_metrics_globals()
        (
            self.meter_provider,
            self.memory_metrics_reader,
        ) = self.create_meter_provider(
            exemplar_filter=AlwaysOnExemplarFilter(),
        )
        metrics_api.set_meter_provider(self.meter_provider)

        self._app = Flask(__name__)
        @self._app.route("/test/")
        def test_route():
            return "Test response"

        self._client = self._app.test_client()

        FlaskInstrumentor().instrument_app(
            self._app,
            meter_provider=self.meter_provider,
        )

    def tearDown(self):
        FlaskInstrumentor().uninstrument()
        super().tearDown()

    def test_duration_metrics_exemplars(self):
        """Should generate exemplars with trace and span IDs for Flask HTTP requests."""
        self._client.get("/test/")  
        self._client.get("/test/")
        self._client.get("/test/")
        
        metrics_data = self.memory_metrics_reader.get_metrics_data()
        self.assertIsNotNone(metrics_data)
        self.assertTrue(len(metrics_data.resource_metrics) > 0)

        duration_metric = None
        metric_names = []
        for resource_metric in metrics_data.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    metric_names.append(metric.name)
                    if metric.name in ["http.server.request.duration", "http.server.duration"]:
                        duration_metric = metric
                        break
                if duration_metric:
                    break
            if duration_metric:
                break
        
        self.assertIsNotNone(duration_metric)        
        data_points = list(duration_metric.data.data_points)
        self.assertTrue(len(data_points) > 0)

        exemplar_count = 0
        for data_point in data_points:
            if hasattr(data_point, 'exemplars') and data_point.exemplars:
                for exemplar in data_point.exemplars:
                    exemplar_count += 1
                    # Exemplar has required fields and valid span context
                    self.assertIsNotNone(exemplar.value)
                    self.assertIsNotNone(exemplar.time_unix_nano)
                    self.assertIsNotNone(exemplar.span_id)
                    self.assertNotEqual(exemplar.span_id, INVALID_SPAN_ID)
                    self.assertIsNotNone(exemplar.trace_id)
                    self.assertNotEqual(exemplar.trace_id, INVALID_TRACE_ID)
                                        
                    # Trace and span ID of exemplar are part of finished spans
                    finished_spans = self.memory_exporter.get_finished_spans()
                    finished_span_ids = [span.context.span_id for span in finished_spans]
                    finished_trace_ids = [span.context.trace_id for span in finished_spans]
                    self.assertIn(exemplar.span_id, finished_span_ids)
                    self.assertIn(exemplar.trace_id, finished_trace_ids)
        
        # At least one exemplar was generated
        self.assertGreater(exemplar_count, 0)
