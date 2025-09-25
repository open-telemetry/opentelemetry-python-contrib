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

import unittest
from unittest import mock

from opentelemetry.instrumentation.openai_agents.utils import (
    get_agent_operation_name,
    get_agent_span_name,
    is_content_enabled,
    is_metrics_enabled,
)


class TestUtils(unittest.TestCase):
    def test_get_agent_operation_name(self):
        """Test get_agent_operation_name function."""
        result = get_agent_operation_name("chat")
        self.assertEqual(result, "openai_agents.chat")

    def test_get_agent_span_name_with_model(self):
        """Test get_agent_span_name function with model."""
        result = get_agent_span_name("chat", "gpt-4")
        self.assertEqual(result, "openai_agents chat gpt-4")

    def test_get_agent_span_name_without_model(self):
        """Test get_agent_span_name function without model."""
        result = get_agent_span_name("chat")
        self.assertEqual(result, "openai_agents chat")

    @mock.patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT": "true"},
    )
    def test_is_content_enabled_true(self):
        """Test is_content_enabled returns True when env var is 'true'."""
        result = is_content_enabled()
        self.assertTrue(result)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT": "false"},
    )
    def test_is_content_enabled_false(self):
        """Test is_content_enabled returns False when env var is 'false'."""
        result = is_content_enabled()
        self.assertFalse(result)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_is_content_enabled_default(self):
        """Test is_content_enabled returns False by default."""
        result = is_content_enabled()
        self.assertFalse(result)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS": "true"},
    )
    def test_is_metrics_enabled_true(self):
        """Test is_metrics_enabled returns True when env var is 'true'."""
        result = is_metrics_enabled()
        self.assertTrue(result)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS": "false"},
    )
    def test_is_metrics_enabled_false(self):
        """Test is_metrics_enabled returns False when env var is 'false'."""
        result = is_metrics_enabled()
        self.assertFalse(result)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_is_metrics_enabled_default(self):
        """Test is_metrics_enabled returns True by default."""
        result = is_metrics_enabled()
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
