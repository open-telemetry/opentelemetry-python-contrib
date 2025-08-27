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
import unittest
from unittest.mock import patch
from uuid import uuid4

import pytest
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.client import (
    llm_start,
    ContentCapturingMode,
    llm_stop,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.handler import (
    llm_start,
    llm_stop,
)
from opentelemetry.util.genai.types import (
    ChatGeneration,
    Message,
)
from opentelemetry.util.genai.utils import get_content_capturing_mode

from opentelemetry import trace


def patch_env_vars(stability_mode, content_capturing):
    def decorator(test_case):
        @patch.dict(
            os.environ,
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: stability_mode,
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: content_capturing,
            },
        )
        def wrapper(*args, **kwargs):
            # Reset state.
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            return test_case(*args, **kwargs)

        return wrapper

    return decorator


class TestVersion(unittest.TestCase):
    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_get_content_capturing_mode_parses_valid_envvar(self):  # pylint: disable=no-self-use
        assert get_content_capturing_mode() == ContentCapturingMode.SPAN_ONLY

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental", content_capturing=""
    )
    def test_empty_content_capturing_envvar(self):  # pylint: disable=no-self-use
        assert get_content_capturing_mode() == ContentCapturingMode.NO_CONTENT

    @patch_env_vars(stability_mode="default", content_capturing="True")
    def test_get_content_capturing_mode_raises_exception_when_semconv_stability_default(
        self,
    ):  # pylint: disable=no-self-use
        with self.assertRaises(ValueError):
            get_content_capturing_mode()

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="INVALID_VALUE",
    )
    def test_get_content_capturing_mode_raises_exception_on_invalid_envvar(
        self,
    ):  # pylint: disable=no-self-use
        with self.assertLogs(level="WARNING") as cm:
            assert (
                get_content_capturing_mode() == ContentCapturingMode.NO_CONTENT
            )
        self.assertEqual(len(cm.output), 1)
        self.assertIn("INVALID_VALUE is not a valid option for ", cm.output[0])

@pytest.fixture
def telemetry_setup():
    """Set up telemetry providers for testing"""
    # Set up in-memory span exporter to capture spans
    memory_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

    # Set the tracer provider
    trace.set_tracer_provider(tracer_provider)

    yield memory_exporter

    # Cleanup
    memory_exporter.clear()
    # Reset to default tracer provider
    trace.set_tracer_provider(trace.NoOpTracerProvider())


def test_llm_start_and_stop_creates_span(
    telemetry_setup: InMemorySpanExporter,
):
    run_id = uuid4()
    message = Message(content="hello world", type="Human", name="message name")
    chat_generation = ChatGeneration(content="hello back", type="AI")

    # Start and stop LLM invocation
    llm_start(
        [message], run_id=run_id, custom_attr="value", system="test-system"
    )
    invocation = llm_stop(
        run_id, chat_generations=[chat_generation], extra="info"
    )

    # Get the spans that were created
    spans = telemetry_setup.get_finished_spans()

    # Verify span was created
    assert len(spans) == 1
    span = spans[0]

    # Verify span properties
    assert span.name == "test-system.chat"
    assert span.kind == trace.SpanKind.CLIENT

    # Verify span attributes
    assert span.attributes.get("gen_ai.operation.name") == "chat"
    assert span.attributes.get("gen_ai.system") == "test-system"
    # Add more attribute checks as needed

    # Verify span timing
    assert span.start_time > 0
    assert span.end_time > span.start_time

    # Verify invocation data
    assert invocation.run_id == run_id
    assert invocation.attributes.get("custom_attr") == "value"
    assert invocation.attributes.get("extra") == "info"
