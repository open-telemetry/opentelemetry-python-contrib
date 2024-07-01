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

from unittest import TestCase
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.aws_lambda import (
    OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT,
    OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION,
    determine_flush_timeout,
    flush,
    is_aws_context_propagation_disabled,
)


class TestDetermineFlushTimeout(TestCase):
    default = 30000
    timeout_var = OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT

    def test_flush_timeout_default(self):
        self.assertEqual(determine_flush_timeout(), self.default)

    @patch.dict("os.environ", {timeout_var: "1000"})
    def test_flush_timeout_env_var(self):
        self.assertEqual(determine_flush_timeout(), 1000)

    @patch.dict("os.environ", {timeout_var: "abc"})
    def test_flush_timeout_env_var_invalid(self):
        self.assertEqual(determine_flush_timeout(), self.default)


class TestIsAWSContextPropagationDisabled(TestCase):
    prop_var = OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION

    def test_non_boolean_override(self):
        result = is_aws_context_propagation_disabled("not_a_boolean")
        self.assertFalse(result)

    def test_boolean_override_true(self):
        result = is_aws_context_propagation_disabled(True)
        self.assertTrue(result)

    def test_boolean_override_false(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertFalse(result)

    @patch.dict("os.environ", {prop_var: "true"})
    def test_env_var_true(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertTrue(result)

    @patch.dict("os.environ", {prop_var: "false"})
    def test_env_var_false(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertFalse(result)

    @patch.dict("os.environ", {prop_var: "1"})
    def test_env_var_one(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertTrue(result)

    @patch.dict("os.environ", {prop_var: "0"})
    def test_env_var_zero(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertFalse(result)

    @patch.dict("os.environ", {prop_var: "t"})
    def test_env_var_t(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertTrue(result)

    @patch.dict("os.environ", {}, clear=True)
    def test_env_var_not_set(self):
        result = is_aws_context_propagation_disabled(False)
        self.assertFalse(result)


class TestFlush(TestCase):
    @patch("time.time", return_value=0)
    @patch(
        "opentelemetry.instrumentation.aws_lambda.determine_flush_timeout",
        return_value=1000,
    )
    def test_successful_flush(self, mock_time, mock_determine_flush_timeout):
        tracer_provider = MagicMock()
        meter_provider = MagicMock()
        tracer_provider.force_flush = MagicMock()
        meter_provider.force_flush = MagicMock()

        flush(tracer_provider, meter_provider)

        self.assertEqual(tracer_provider.force_flush.call_count, 1)
        tracer_provider.force_flush.assert_called_once_with(1000)
        self.assertEqual(meter_provider.force_flush.call_count, 1)
        meter_provider.force_flush.assert_called_once_with(1000)

    @patch("time.time", return_value=0)
    @patch(
        "opentelemetry.instrumentation.aws_lambda.determine_flush_timeout",
        return_value=1000,
    )
    def test_missing_force_flush_in_tracer_provider(
        self, mock_time, mock_determine_flush_timeout
    ):
        tracer_provider = MagicMock()
        del tracer_provider.force_flush  # Remove force_flush method
        meter_provider = MagicMock()
        meter_provider.force_flush = MagicMock()

        flush(tracer_provider, meter_provider)

        self.assertNotIn("force_flush", dir(tracer_provider))
        meter_provider.force_flush.assert_called_once_with(1000)

    @patch("time.time", return_value=0)
    @patch(
        "opentelemetry.instrumentation.aws_lambda.determine_flush_timeout",
        return_value=1000,
    )
    def test_missing_force_flush_in_meter_provider(
        self, mock_time, mock_determine_flush_timeout
    ):
        tracer_provider = MagicMock()
        tracer_provider.force_flush = MagicMock()
        meter_provider = MagicMock()
        del meter_provider.force_flush  # Remove force_flush method

        flush(tracer_provider, meter_provider)

        self.assertNotIn("force_flush", dir(meter_provider))
        tracer_provider.force_flush.assert_called_once_with(1000)

    @patch("time.time", return_value=0)
    @patch(
        "opentelemetry.instrumentation.aws_lambda.determine_flush_timeout",
        return_value=1000,
    )
    def test_exception_in_force_flush_tracer_provider(
        self, mock_time, mock_determine_flush_timeout
    ):
        tracer_provider = MagicMock()
        tracer_provider.force_flush = MagicMock(
            side_effect=Exception("Tracer flush exception")
        )
        meter_provider = MagicMock()
        meter_provider.force_flush = MagicMock()

        flush(tracer_provider, meter_provider)

        self.assertEqual(meter_provider.force_flush.call_count, 1)
        meter_provider.force_flush.assert_called_once_with(1000)

    @patch("time.time", return_value=0)
    @patch(
        "opentelemetry.instrumentation.aws_lambda.determine_flush_timeout",
        return_value=1000,
    )
    def test_exception_in_force_flush_meter_provider(
        self, mock_time, mock_determine_flush_timeout
    ):
        tracer_provider = MagicMock()
        tracer_provider.force_flush = MagicMock()
        meter_provider = MagicMock()
        meter_provider.force_flush = MagicMock(
            side_effect=Exception("Meter flush exception")
        )

        flush(tracer_provider, meter_provider)

        self.assertEqual(tracer_provider.force_flush.call_count, 1)
        tracer_provider.force_flush.assert_called_once_with(1000)
