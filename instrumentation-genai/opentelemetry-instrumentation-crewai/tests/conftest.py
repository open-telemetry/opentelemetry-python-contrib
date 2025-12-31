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

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function")
def span_exporter():
    """Create an in-memory span exporter for testing."""
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture(scope="function")
def tracer_provider(span_exporter):
    """Create a tracer provider with the in-memory exporter."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    return provider


@pytest.fixture(scope="function")
def enable_content_capture():
    """Enable content capture for tests."""
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
    yield
    os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)


@pytest.fixture(scope="function")
def disable_content_capture():
    """Disable content capture for tests."""
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
    yield
    os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)
