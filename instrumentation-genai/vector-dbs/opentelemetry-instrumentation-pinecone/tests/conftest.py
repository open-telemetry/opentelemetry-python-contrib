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

import os

import pytest

# Skip all tests if pinecone is not installed
try:
    import pinecone  # noqa: F401

    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    collect_ignore_glob = ["test_*.py"]


if PINECONE_AVAILABLE:
    from opentelemetry import metrics, trace
    from opentelemetry.instrumentation.pinecone import PineconeInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    pytest_plugins = []

    @pytest.fixture(scope="session")
    def span_exporter():
        exporter = InMemorySpanExporter()
        processor = SimpleSpanProcessor(exporter)

        provider = TracerProvider()
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        return exporter

    @pytest.fixture(scope="session")
    def metrics_reader():
        resource = Resource.create()
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader], resource=resource)
        metrics.set_meter_provider(provider)

        return reader

    @pytest.fixture(autouse=True, scope="session")
    def instrument(span_exporter, metrics_reader):
        PineconeInstrumentor().instrument()

    @pytest.fixture(autouse=True)
    def clear_exporter(span_exporter):
        span_exporter.clear()

    @pytest.fixture(autouse=True)
    def environment():
        os.environ.setdefault("PINECONE_API_KEY", "test-api-key")
        os.environ.setdefault("PINECONE_ENVIRONMENT", "gcp-starter")

    @pytest.fixture(scope="module")
    def vcr_config():
        return {"filter_headers": ["authorization", "api-key"]}
