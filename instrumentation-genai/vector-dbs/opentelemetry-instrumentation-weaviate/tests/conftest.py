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

# Skip all tests if weaviate is not installed
try:
    import weaviate  # noqa: F401

    WEAVIATE_AVAILABLE = True
except ImportError:
    WEAVIATE_AVAILABLE = False
    collect_ignore_glob = ["test_*.py"]


def pytest_addoption(parser):
    parser.addoption(
        "--with_grpc",
        action="store_true",
        default=False,
        help=(
            "Run the tests only in case --with_grpc is specified on the command line. "
            "For such tests a running weaviate instance is required."
        ),
    )


def pytest_runtest_setup(item):
    if "with_grpc" in item.keywords and not item.config.getoption("--with_grpc"):
        pytest.skip("need --with_grpc option to run this test")


if WEAVIATE_AVAILABLE:
    from opentelemetry import trace
    from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    pytest_plugins = []

    @pytest.fixture(scope="session")
    def exporter():
        exporter = InMemorySpanExporter()
        processor = SimpleSpanProcessor(exporter)

        provider = TracerProvider()
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        WeaviateInstrumentor().instrument()

        return exporter

    @pytest.fixture(autouse=True)
    def clear_exporter(exporter):
        exporter.clear()

    @pytest.fixture(autouse=True)
    def environment():
        os.environ.setdefault("WEAVIATE_API_KEY", "test-api-key")
        os.environ.setdefault(
            "WEAVIATE_CLUSTER_URL", "https://test-cluster.weaviate.network"
        )

    @pytest.fixture(scope="module")
    def vcr_config():
        return {
            "filter_headers": ["authorization", "x-openai-api-key"],
        }
