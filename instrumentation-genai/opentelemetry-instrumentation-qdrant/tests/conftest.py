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

"""Unit tests configuration module."""

import pytest
from opentelemetry import trace
from opentelemetry.instrumentation.qdrant import QdrantInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function")
def span_exporter():
    """Create and return an InMemorySpanExporter."""
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function")
def tracer_provider(span_exporter):
    """Create and return a TracerProvider with the span exporter."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function", autouse=True)
def instrument(tracer_provider):
    """Instrument Qdrant and set up tracing."""
    trace.set_tracer_provider(tracer_provider)
    instrumentor = QdrantInstrumentor()
    instrumentor.instrument()
    yield instrumentor
    instrumentor.uninstrument()


@pytest.fixture(autouse=True)
def clear_exporter(span_exporter):
    """Clear the exporter after each test."""
    yield
    span_exporter.clear()
