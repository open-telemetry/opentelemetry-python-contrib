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
# pylint: disable=redefined-outer-name

import json
import os

import pytest
import yaml
from anthropic import Anthropic

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)


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
    return provider


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


@pytest.fixture(autouse=True)
def environment():
    """Set up environment variables for testing."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_api_key"


@pytest.fixture
def anthropic_client():
    """Create and return an Anthropic client."""
    return Anthropic()


@pytest.fixture(scope="module")
def vcr_config():
    """Configure VCR for recording/replaying HTTP interactions."""
    return {
        "filter_headers": [
            ("x-api-key", "test_anthropic_api_key"),
            ("authorization", "Bearer test_anthropic_api_key"),
        ],
        "decode_compressed_response": True,
        "before_record_response": scrub_response_headers,
    }


@pytest.fixture(scope="function")
def instrument_no_content(tracer_provider, logger_provider, meter_provider):
    """Instrument Anthropic without content capture."""
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update(
        {
            OTEL_SEMCONV_STABILITY_OPT_IN: "stable",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "NO_CONTENT",
        }
    )

    instrumentor = AnthropicInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(tracer_provider, logger_provider, meter_provider):
    """Instrument Anthropic with content capture enabled."""
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update(
        {
            OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "SPAN_ONLY",
        }
    )
    instrumentor = AnthropicInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    instrumentor.uninstrument()


@pytest.fixture
def instrument_anthropic(tracer_provider, logger_provider, meter_provider):
    """Fixture to instrument Anthropic with test providers."""
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
    AnthropicInstrumentor().uninstrument()


class LiteralBlockScalar(str):
    """Formats the string as a literal block scalar."""


def literal_block_scalar_presenter(dumper, data):
    """Represents a scalar string as a literal block, via '|' syntax."""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlockScalar, literal_block_scalar_presenter)


def process_string_value(string_value):
    """Pretty-prints JSON or returns long strings as a LiteralBlockScalar."""
    try:
        json_data = json.loads(string_value)
        return LiteralBlockScalar(json.dumps(json_data, indent=2))
    except (ValueError, TypeError):
        if len(string_value) > 80:
            return LiteralBlockScalar(string_value)
    return string_value


def convert_body_to_literal(data):
    """Searches the data for body strings, attempting to pretty-print JSON."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "body" and isinstance(value, dict) and "string" in value:
                value["string"] = process_string_value(value["string"])
            elif key == "body" and isinstance(value, str):
                data[key] = process_string_value(value)
            else:
                convert_body_to_literal(value)
    elif isinstance(data, list):
        for idx, choice in enumerate(data):
            data[idx] = convert_body_to_literal(choice)
    return data


class PrettyPrintJSONBody:
    """This makes request and response body recordings more readable."""

    @staticmethod
    def serialize(cassette_dict):
        cassette_dict = convert_body_to_literal(cassette_dict)
        return yaml.dump(
            cassette_dict, default_flow_style=False, allow_unicode=True
        )

    @staticmethod
    def deserialize(cassette_string):
        return yaml.load(cassette_string, Loader=yaml.Loader)


@pytest.fixture(scope="module", autouse=True)
def fixture_vcr(vcr):
    """Register the VCR serializer."""
    vcr.register_serializer("yaml", PrettyPrintJSONBody)
    return vcr


_SCRUBBED_RESPONSE_HEADERS = frozenset(
    {
        "anthropic-organization-id",
    }
)


def scrub_response_headers(response):
    """Scrub sensitive headers from recorded responses."""
    headers = response.get("headers", {})
    for header in _SCRUBBED_RESPONSE_HEADERS:
        headers.pop(header, None)
    return response
