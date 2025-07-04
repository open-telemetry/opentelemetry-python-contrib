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

import os
from unittest import TestCase
from unittest.mock import Mock, patch

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _set_status,
    _StabilityMode,
)
from opentelemetry.trace.status import StatusCode


def stability_mode(mode):
    def decorator(test_case):
        @patch.dict(os.environ, {OTEL_SEMCONV_STABILITY_OPT_IN: mode})
        def wrapper(*args, **kwargs):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            return test_case(*args, **kwargs)

        return wrapper

    return decorator


class TestOpenTelemetrySemConvStability(TestCase):
    @stability_mode("")
    def test_default_mode(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.DEFAULT,
        )
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DEFAULT,
        )

    @stability_mode("http")
    def test_http_stable_mode(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.HTTP,
        )

    @stability_mode("http/dup")
    def test_http_dup_mode(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.HTTP_DUP,
        )

    @stability_mode("database")
    def test_database_stable_mode(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DATABASE,
        )

    @stability_mode("database/dup")
    def test_database_dup_mode(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DATABASE_DUP,
        )

    @stability_mode("database,http")
    def test_multiple_stability_database_http_modes(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DATABASE,
        )
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.HTTP,
        )

    @stability_mode("database,http/dup")
    def test_multiple_stability_database_http_dup_modes(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DATABASE,
        )
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.HTTP_DUP,
        )

    @stability_mode("database/dup,http")
    def test_multiple_stability_database_dup_http_stable_modes(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DATABASE_DUP,
        )
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.HTTP,
        )

    @stability_mode("database,database/dup,http,http/dup")
    def test_stability_mode_dup_precedence(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.DATABASE
            ),
            _StabilityMode.DATABASE_DUP,
        )
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.HTTP
            ),
            _StabilityMode.HTTP_DUP,
        )


class TestOpenTelemetrySemConvStabilityHTTP(TestCase):
    def test_set_status_for_non_http_code_with_recording_span(self):
        span = Mock()
        span.is_recording.return_value = True
        metric_attributes = {}
        _set_status(
            span,
            metric_attributes,
            -1,
            "Exception",
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )

        self.assertIsNone(metric_attributes.get("error.type"))
        span.set_attribute.assert_not_called()
        status_call = span.set_status.call_args[0][0]
        self.assertEqual(status_call.status_code, StatusCode.ERROR)
        self.assertEqual(
            status_call.description, "Non-integer HTTP status: " + "Exception"
        )

    def test_status_code_http_default(self):
        span = Mock()
        metrics_attributes = {}
        _set_status(
            span=span,
            metrics_attributes=metrics_attributes,
            status_code=404,
            status_code_str="404",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        # Verify only old conventions are emitted
        span.set_attribute.assert_called_with("http.status_code", 404)
        self.assertIn("http.status_code", metrics_attributes)
        self.assertNotIn("http.response_status_code", metrics_attributes)

    def test_status_code_http_stable(self):
        span = Mock()
        metrics_attributes = {}
        _set_status(
            span=span,
            metrics_attributes=metrics_attributes,
            status_code=200,
            status_code_str="200",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.HTTP,
        )
        # Verify only new conventions are emitted
        span.set_attribute.assert_called_with("http.response.status_code", 200)
        self.assertIn("http.response.status_code", metrics_attributes)
        self.assertNotIn("http.status_code", metrics_attributes)

    def test_status_code_http_dup(self):
        span = Mock()
        metrics_attributes = {}
        _set_status(
            span=span,
            metrics_attributes=metrics_attributes,
            status_code=500,
            status_code_str="500",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.HTTP_DUP,
        )
        # Verify both old and new conventions are emitted
        span.set_attribute.assert_any_call("http.status_code", 500)
        span.set_attribute.assert_any_call("http.response.status_code", 500)
        self.assertIn("http.status_code", metrics_attributes)
        self.assertIn("http.response.status_code", metrics_attributes)

    def test_error_status_code_new_mode(self):
        span = Mock()
        metrics_attributes = {}
        _set_status(
            span=span,
            metrics_attributes=metrics_attributes,
            status_code=500,
            status_code_str="500",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.HTTP,
        )
        # Verify error type is set for new conventions
        span.set_attribute.assert_any_call("error.type", "500")
        self.assertIn("error.type", metrics_attributes)
        self.assertEqual(metrics_attributes["error.type"], "500")

    def test_non_recording_span(self):
        span = Mock()
        span.is_recording.return_value = False
        metrics_attributes = {}
        _set_status(
            span=span,
            metrics_attributes=metrics_attributes,
            status_code=200,
            status_code_str="200",
            server_span=True,
            sem_conv_opt_in_mode=_StabilityMode.HTTP_DUP,
        )
        # Verify no span attributes are set if not recording
        span.set_attribute.assert_not_called()
        span.set_status.assert_not_called()
        # Verify status code set for metrics independent of tracing decision
        self.assertIn("http.status_code", metrics_attributes)
        self.assertIn("http.response.status_code", metrics_attributes)
