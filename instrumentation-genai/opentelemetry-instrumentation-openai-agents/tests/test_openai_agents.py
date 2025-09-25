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

from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.test.test_base import TestBase


class TestOpenAIAgentsInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        self.instrumentor = OpenAIAgentsInstrumentor()

    def tearDown(self):
        super().tearDown()
        self.instrumentor.uninstrument()

    def test_instrument(self):
        """Test that the instrumentor can be enabled."""
        self.instrumentor.instrument()
        self.assertTrue(self.instrumentor.is_instrumented_by_opentelemetry)

    def test_uninstrument(self):
        """Test that the instrumentor can be disabled."""
        self.instrumentor.instrument()
        self.instrumentor.uninstrument()
        self.assertFalse(self.instrumentor.is_instrumented_by_opentelemetry)

    def test_instrumentation_dependencies(self):
        """Test that instrumentation dependencies are returned."""
        dependencies = self.instrumentor.instrumentation_dependencies()
        self.assertIsInstance(dependencies, tuple)
        self.assertEqual(dependencies, ("openai-agent >= 0.1.0",))

    @mock.patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT": "true"},
    )
    def test_capture_content_enabled(self):
        """Test that content capture can be enabled via environment variable."""
        self.instrumentor.instrument()
        # The test passes if no exception is raised during instrumentation
        self.assertTrue(self.instrumentor.is_instrumented_by_opentelemetry)

    @mock.patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS": "false"},
    )
    def test_metrics_disabled(self):
        """Test that metrics capture can be disabled via environment variable."""
        self.instrumentor.instrument()
        # The test passes if no exception is raised during instrumentation
        self.assertTrue(self.instrumentor.is_instrumented_by_opentelemetry)


if __name__ == "__main__":
    unittest.main()
