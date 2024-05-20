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

from opentelemetry.instrumentation.aws_lambda import determine_flush_timeout
from opentelemetry.instrumentation.aws_lambda import (
    OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT,
)
from unittest.mock import patch


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
