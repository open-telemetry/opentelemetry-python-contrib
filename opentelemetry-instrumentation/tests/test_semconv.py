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
    _LEGACY_SCHEMA_VERSION,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _get_schema_url_for_signal_types,
    _get_schema_version_for_opt_in_mode,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _set_db_name,
    _set_db_operation,
    _set_db_statement,
    _set_db_system,
    _set_db_user,
    _set_status,
    _StabilityMode,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_OPERATION,
    DB_STATEMENT,
    DB_SYSTEM,
    DB_USER,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_OPERATION_NAME,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
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
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.GEN_AI
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

    @stability_mode("gen_ai_latest_experimental")
    def test_genai_latest_experimental(self):
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.GEN_AI
            ),
            _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL,
        )

    @stability_mode("database,http,gen_ai_latest_experimental")
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
        self.assertEqual(
            _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
                _OpenTelemetryStabilitySignalType.GEN_AI
            ),
            _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL,
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


class TestOpenTelemetrySemConvSchemaUrl(TestCase):
    @stability_mode("")
    def test_get_schema_version_for_opt_in_mode_default(self):
        version = _get_schema_version_for_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP, _StabilityMode.DEFAULT
        )
        self.assertEqual(version, _LEGACY_SCHEMA_VERSION)

        version = _get_schema_version_for_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE, _StabilityMode.DEFAULT
        )
        self.assertEqual(version, _LEGACY_SCHEMA_VERSION)

        version = _get_schema_version_for_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI, _StabilityMode.DEFAULT
        )
        self.assertEqual(version, _LEGACY_SCHEMA_VERSION)

    @stability_mode("")
    def test_get_schema_version_for_opt_in_mode_http_stable(self):
        version = _get_schema_version_for_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP, _StabilityMode.HTTP
        )
        self.assertEqual(version, "1.21.0")

    @stability_mode("")
    def test_get_schema_version_for_opt_in_mode_database_stable(self):
        version = _get_schema_version_for_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE, _StabilityMode.DATABASE
        )
        self.assertEqual(version, "1.25.0")

    @stability_mode("")
    def test_get_schema_version_for_opt_in_mode_gen_ai_stable(self):
        version = _get_schema_version_for_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
            _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL,
        )
        self.assertEqual(version, "1.26.0")

    @stability_mode("")
    def test_get_schema_url_for_signal_types_single_http_default(self):
        url = _get_schema_url_for_signal_types(
            [_OpenTelemetryStabilitySignalType.HTTP]
        )
        self.assertEqual(
            url, f"https://opentelemetry.io/schemas/{_LEGACY_SCHEMA_VERSION}"
        )

    @stability_mode("http")
    def test_get_schema_url_for_signal_types_single_http_stable(self):
        url = _get_schema_url_for_signal_types(
            [_OpenTelemetryStabilitySignalType.HTTP]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.21.0")

    @stability_mode("database")
    def test_get_schema_url_for_signal_types_single_database_stable(self):
        url = _get_schema_url_for_signal_types(
            [_OpenTelemetryStabilitySignalType.DATABASE]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.25.0")

    @stability_mode("http,database")
    def test_get_schema_url_for_signal_types_multiple_both_stable(self):
        # DATABASE has higher version (1.25.0) than HTTP (1.21.0)
        url = _get_schema_url_for_signal_types(
            [
                _OpenTelemetryStabilitySignalType.HTTP,
                _OpenTelemetryStabilitySignalType.DATABASE,
            ]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.25.0")

    @stability_mode("http")
    def test_get_schema_url_for_signal_types_mixed_modes(self):
        # HTTP is stable (1.21.0), DATABASE is default (1.11.0)
        # Should return HTTP version as it's higher
        url = _get_schema_url_for_signal_types(
            [
                _OpenTelemetryStabilitySignalType.HTTP,
                _OpenTelemetryStabilitySignalType.DATABASE,
            ]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.21.0")

    @stability_mode("database")
    def test_get_schema_url_for_signal_types_database_only_stable(self):
        # DATABASE is stable (1.25.0), HTTP is default (1.11.0)
        # Should return DATABASE version as it's highest
        url = _get_schema_url_for_signal_types(
            [
                _OpenTelemetryStabilitySignalType.HTTP,
                _OpenTelemetryStabilitySignalType.DATABASE,
            ]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.25.0")

    @stability_mode("")
    def test_get_schema_url_for_signal_types_empty_list(self):
        url = _get_schema_url_for_signal_types([])
        self.assertEqual(
            url, f"https://opentelemetry.io/schemas/{_LEGACY_SCHEMA_VERSION}"
        )

    @stability_mode("http/dup,database/dup")
    def test_get_schema_url_for_signal_types_dup_modes(self):
        url = _get_schema_url_for_signal_types(
            [
                _OpenTelemetryStabilitySignalType.HTTP,
                _OpenTelemetryStabilitySignalType.DATABASE,
            ]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.25.0")

    @stability_mode("http,database,gen_ai_latest_experimental")
    def test_get_schema_url_for_signal_types_with_gen_ai(self):
        # GEN_AI should be highest at 1.26.0
        url = _get_schema_url_for_signal_types(
            [
                _OpenTelemetryStabilitySignalType.HTTP,
                _OpenTelemetryStabilitySignalType.DATABASE,
                _OpenTelemetryStabilitySignalType.GEN_AI,
            ]
        )
        self.assertEqual(url, "https://opentelemetry.io/schemas/1.26.0")


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


class TestOpenTelemetrySemConvStabilityDatabase(TestCase):
    def test_db_system_default(self):
        result = {}
        _set_db_system(
            result, "postgresql", sem_conv_opt_in_mode=_StabilityMode.DEFAULT
        )
        self.assertIn(DB_SYSTEM, result)
        self.assertEqual(result[DB_SYSTEM], "postgresql")
        self.assertNotIn(DB_SYSTEM_NAME, result)

    def test_db_system_database_stable(self):
        result = {}
        _set_db_system(
            result, "postgresql", sem_conv_opt_in_mode=_StabilityMode.DATABASE
        )
        self.assertNotIn(DB_SYSTEM, result)
        self.assertIn(DB_SYSTEM_NAME, result)
        self.assertEqual(result[DB_SYSTEM_NAME], "postgresql")

    def test_db_system_database_dup(self):
        result = {}
        _set_db_system(
            result,
            "postgresql",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP,
        )
        self.assertIn(DB_SYSTEM, result)
        self.assertEqual(result[DB_SYSTEM], "postgresql")
        self.assertIn(DB_SYSTEM_NAME, result)
        self.assertEqual(result[DB_SYSTEM_NAME], "postgresql")

    def test_db_system_none_value(self):
        result = {}
        _set_db_system(
            result, None, sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP
        )
        self.assertNotIn(DB_SYSTEM, result)
        self.assertNotIn(DB_SYSTEM_NAME, result)

    def test_db_name_default(self):
        result = {}
        _set_db_name(
            result, "my_database", sem_conv_opt_in_mode=_StabilityMode.DEFAULT
        )
        self.assertIn(DB_NAME, result)
        self.assertEqual(result[DB_NAME], "my_database")
        self.assertNotIn(DB_NAMESPACE, result)

    def test_db_name_database_stable(self):
        result = {}
        _set_db_name(
            result, "my_database", sem_conv_opt_in_mode=_StabilityMode.DATABASE
        )
        self.assertNotIn(DB_NAME, result)
        self.assertIn(DB_NAMESPACE, result)
        self.assertEqual(result[DB_NAMESPACE], "my_database")

    def test_db_name_database_dup(self):
        result = {}
        _set_db_name(
            result,
            "my_database",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP,
        )
        self.assertIn(DB_NAME, result)
        self.assertEqual(result[DB_NAME], "my_database")
        self.assertIn(DB_NAMESPACE, result)
        self.assertEqual(result[DB_NAMESPACE], "my_database")

    def test_db_name_none_value(self):
        result = {}
        _set_db_name(
            result, None, sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP
        )
        self.assertNotIn(DB_NAME, result)
        self.assertNotIn(DB_NAMESPACE, result)

    def test_db_statement_default(self):
        result = {}
        _set_db_statement(
            result,
            "SELECT * FROM users",
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        self.assertIn(DB_STATEMENT, result)
        self.assertEqual(result[DB_STATEMENT], "SELECT * FROM users")
        self.assertNotIn(DB_QUERY_TEXT, result)

    def test_db_statement_database_stable(self):
        result = {}
        _set_db_statement(
            result,
            "SELECT * FROM users",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE,
        )
        self.assertNotIn(DB_STATEMENT, result)
        self.assertIn(DB_QUERY_TEXT, result)
        self.assertEqual(result[DB_QUERY_TEXT], "SELECT * FROM users")

    def test_db_statement_database_dup(self):
        result = {}
        _set_db_statement(
            result,
            "SELECT * FROM users",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP,
        )
        self.assertIn(DB_STATEMENT, result)
        self.assertEqual(result[DB_STATEMENT], "SELECT * FROM users")
        self.assertIn(DB_QUERY_TEXT, result)
        self.assertEqual(result[DB_QUERY_TEXT], "SELECT * FROM users")

    def test_db_statement_none_value(self):
        result = {}
        _set_db_statement(
            result, None, sem_conv_opt_in_mode=_StabilityMode.DEFAULT
        )
        self.assertNotIn(DB_STATEMENT, result)
        self.assertNotIn(DB_QUERY_TEXT, result)

    def test_db_user_default(self):
        result = {}
        _set_db_user(
            result, "admin", sem_conv_opt_in_mode=_StabilityMode.DEFAULT
        )
        self.assertIn(DB_USER, result)
        self.assertEqual(result[DB_USER], "admin")

    def test_db_user_database_stable(self):
        result = {}
        _set_db_user(
            result, "admin", sem_conv_opt_in_mode=_StabilityMode.DATABASE
        )
        # No new attribute - db.user was removed with no replacement
        self.assertNotIn(DB_USER, result)

    def test_db_user_database_dup(self):
        result = {}
        _set_db_user(
            result,
            "admin",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP,
        )
        self.assertIn(DB_USER, result)
        self.assertEqual(result[DB_USER], "admin")

    def test_db_user_none_value(self):
        result = {}
        _set_db_user(result, None, sem_conv_opt_in_mode=_StabilityMode.DEFAULT)
        self.assertNotIn(DB_USER, result)

    def test_db_operation_default(self):
        result = {}
        _set_db_operation(
            result,
            "SELECT",
            sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
        )
        self.assertIn(DB_OPERATION, result)
        self.assertEqual(result[DB_OPERATION], "SELECT")
        self.assertNotIn(DB_OPERATION_NAME, result)

    def test_db_operation_database_stable(self):
        result = {}
        _set_db_operation(
            result,
            "SELECT",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE,
        )
        self.assertNotIn(DB_OPERATION, result)
        self.assertIn(DB_OPERATION_NAME, result)
        self.assertEqual(result[DB_OPERATION_NAME], "SELECT")

    def test_db_operation_database_dup(self):
        result = {}
        _set_db_operation(
            result,
            "SELECT",
            sem_conv_opt_in_mode=_StabilityMode.DATABASE_DUP,
        )
        self.assertIn(DB_OPERATION, result)
        self.assertEqual(result[DB_OPERATION], "SELECT")
        self.assertIn(DB_OPERATION_NAME, result)
        self.assertEqual(result[DB_OPERATION_NAME], "SELECT")

    def test_db_operation_none_value(self):
        result = {}
        _set_db_operation(
            result, None, sem_conv_opt_in_mode=_StabilityMode.DEFAULT
        )
        self.assertNotIn(DB_OPERATION, result)
        self.assertNotIn(DB_OPERATION_NAME, result)
