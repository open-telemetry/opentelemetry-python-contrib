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

from opentelemetry.instrumentation.aws_lambda import (
    determine_flush_timeout,
    is_aws_context_propagation_disabled,
)
from opentelemetry.instrumentation.aws_lambda import (
    OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT,
    OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION,
)
from unittest.mock import patch
from unittest import TestCase


class TestDetermineFlushTimeout:
    default = 30000
    timeout_var = OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT

    def test_flush_timeout_default(self):
        assert determine_flush_timeout() == self.default

    @patch.dict("os.environ", {timeout_var: "1000"})
    def test_flush_timeout_env_var(self):
        assert determine_flush_timeout() == 1000

    @patch.dict("os.environ", {timeout_var: "abc"})
    def test_flush_timeout_env_var_invalid(self):
        assert determine_flush_timeout() == self.default


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
