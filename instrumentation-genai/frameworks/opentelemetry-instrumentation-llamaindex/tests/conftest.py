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

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture
def tracer_provider():
    """Create a tracer provider for testing."""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    return provider


@pytest.fixture
def memory_exporter(tracer_provider):
    """Create an in-memory span exporter for testing."""
    exporter = InMemorySpanExporter()
    tracer_provider.add_span_processor(
        trace.get_tracer_provider().get_tracer(__name__)._real_span_processor
        if hasattr(
            trace.get_tracer_provider().get_tracer(__name__), "_real_span_processor"
        )
        else None
    )
    return exporter


@pytest.fixture
def span_exporter():
    """Create a simple in-memory span exporter."""
    return InMemorySpanExporter()


@pytest.fixture
def setup_tracing(span_exporter):
    """Set up tracing with in-memory exporter."""
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    yield provider
    span_exporter.clear()
