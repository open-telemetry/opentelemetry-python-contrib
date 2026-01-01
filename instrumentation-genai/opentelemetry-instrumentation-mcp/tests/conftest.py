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

"""Test configuration module for MCP instrumentation."""

import pytest
from opentelemetry import trace
from opentelemetry.instrumentation.mcp import MCPInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

pytest_plugins = []


@pytest.fixture(scope="session")
def span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="session")
def tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    yield provider
    provider.shutdown()


@pytest.fixture(autouse=True)
def instrument_mcp(tracer_provider, span_exporter):
    instrumenter = MCPInstrumentor()
    instrumenter.instrument(tracer_provider=tracer_provider)
    try:
        yield
    finally:
        instrumenter.uninstrument()
        span_exporter.clear()
