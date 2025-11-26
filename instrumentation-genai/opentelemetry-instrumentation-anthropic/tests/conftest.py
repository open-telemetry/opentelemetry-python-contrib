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

"""Test configuration and fixtures for Anthropic instrumentation tests."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


@pytest.fixture
def span_exporter():
    """Create and return an in-memory span exporter."""
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture
def log_exporter():
    """Create and return an in-memory log exporter."""
    exporter = InMemoryLogExporter()
    yield exporter
    exporter.clear()


@pytest.fixture
def metric_reader():
    """Create and return an in-memory metric reader."""
    reader = InMemoryMetricReader()
    yield reader


@pytest.fixture
def tracer_provider(span_exporter):
    """Create and configure a tracer provider with in-memory export."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    yield provider


@pytest.fixture
def logger_provider(log_exporter):
    """Create and configure a logger provider with in-memory export."""
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    yield provider


@pytest.fixture
def meter_provider(metric_reader):
    """Create and configure a meter provider with in-memory metrics."""
    provider = MeterProvider(metric_readers=[metric_reader])
    yield provider


@pytest.fixture
def instrument_anthropic(tracer_provider, logger_provider, meter_provider):
    """Fixture to instrument Anthropic with test providers."""
    from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

    instrumentor = AnthropicInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    yield instrumentor
    instrumentor.uninstrument()


@pytest.fixture
def uninstrument_anthropic():
    """Fixture to ensure Anthropic is uninstrumented after test."""
    yield
    from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

    AnthropicInstrumentor().uninstrument()

