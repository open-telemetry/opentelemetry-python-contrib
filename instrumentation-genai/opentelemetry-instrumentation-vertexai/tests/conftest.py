"""Unit tests configuration module."""

import asyncio
import json
import os
import re
from typing import (
    Any,
    Callable,
    Generator,
    Mapping,
    MutableMapping,
    Protocol,
    TypeVar,
)

import pytest
import vertexai
import yaml
from google.auth.aio.credentials import (
    AnonymousCredentials as AsyncAnonymousCredentials,
)
from google.auth.credentials import AnonymousCredentials
from google.cloud.aiplatform.initializer import _set_async_rest_credentials
from typing_extensions import Concatenate, ParamSpec
from vcr import VCR
from vcr.record_mode import RecordMode
from vcr.request import Request
from vertexai.generative_models import (
    GenerativeModel,
)

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.instrumentation.vertexai.utils import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.sdk._logs import LoggerProvider

# Backward compatibility for InMemoryLogExporter -> InMemoryLogRecordExporter rename
try:
    from opentelemetry.sdk._logs.export import (  # pylint: disable=no-name-in-module
        InMemoryLogRecordExporter,
        SimpleLogRecordProcessor,
    )
except ImportError:
    # Fallback to old name for compatibility with older SDK versions
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter as InMemoryLogRecordExporter,
    )
    from opentelemetry.sdk._logs.export import (
        SimpleLogRecordProcessor,
    )
from opentelemetry.sdk.metrics import (
    MeterProvider,
)
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

FAKE_PROJECT = "fake-project"


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogRecordExporter()
    yield exporter


@pytest.fixture(scope="function", name="metric_reader")
def fixture_metric_reader():
    exporter = InMemoryMetricReader()
    yield exporter


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function", name="logger_provider")
def fixture_logger_provider(log_exporter):
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))

    return provider


@pytest.fixture(scope="function", name="meter_provider")
def fixture_meter_provider(metric_reader):
    return MeterProvider(
        metric_readers=[metric_reader],
    )


@pytest.fixture(autouse=True)
def vertexai_init(vcr: VCR) -> None:
    # When not recording (in CI), don't do any auth. That prevents trying to read application
    # default credentials from the filesystem or metadata server and oauth token exchange. This
    # is not the interesting part of our instrumentation to test.
    credentials = None
    project = None
    if vcr.record_mode == RecordMode.NONE:
        credentials = AnonymousCredentials()
        project = FAKE_PROJECT
    vertexai.init(
        api_transport="rest", credentials=credentials, project=project
    )


@pytest.fixture(scope="function")
def instrument_no_content(
    tracer_provider, logger_provider, meter_provider, request
):
    # Reset global state..
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update({OTEL_SEMCONV_STABILITY_OPT_IN: "stable"})
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "False"}
    )

    instrumentor = VertexAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_no_content_with_experimental_semconvs(
    tracer_provider, logger_provider, meter_provider, request
):
    # Reset global state..
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update(
        {OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental"}
    )
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "NO_CONTENT"}
    )

    instrumentor = VertexAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_experimental_semconvs(
    tracer_provider, logger_provider, meter_provider
):
    # Reset global state..
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update(
        {OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental"}
    )
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "SPAN_AND_EVENT"}
    )
    instrumentor = VertexAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_upload_hook(
    tracer_provider, logger_provider, meter_provider
):
    # Reset global state..
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update(
        {
            OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
            "OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK": "upload",
            "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH": "memory://",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "SPAN_AND_EVENT",
        }
    )
    instrumentor = VertexAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop("OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK", None)
    os.environ.pop("OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH", None)
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(
    tracer_provider, logger_provider, meter_provider, request
):
    # Reset global state..
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ.update({OTEL_SEMCONV_STABILITY_OPT_IN: "stable"})
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "True"}
    )
    instrumentor = VertexAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(scope="module")
def vcr_config():
    filter_header_regexes = [
        r"X-.*",
        "Server",
        "Date",
        "Expires",
        "Authorization",
    ]

    def filter_headers(headers: Mapping[str, str]) -> Mapping[str, str]:
        return {
            key: val
            for key, val in headers.items()
            if not any(
                re.match(filter_re, key, re.IGNORECASE)
                for filter_re in filter_header_regexes
            )
        }

    def before_record_cb(request: Request):
        request.headers = filter_headers(request.headers)
        request.uri = re.sub(
            r"/projects/[^/]+/", "/projects/fake-project/", request.uri
        )
        return request

    def before_response_cb(response: MutableMapping[str, Any]):
        response["headers"] = filter_headers(response["headers"])
        return response

    return {
        "decode_compressed_response": True,
        "before_record_request": before_record_cb,
        "before_record_response": before_response_cb,
        "ignore_hosts": ["oauth2.googleapis.com"],
    }


class LiteralBlockScalar(str):
    """Formats the string as a literal block scalar, preserving whitespace and
    without interpreting escape characters"""


def literal_block_scalar_presenter(dumper, data):
    """Represents a scalar string as a literal block, via '|' syntax"""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlockScalar, literal_block_scalar_presenter)


def process_string_value(string_value):
    """Pretty-prints JSON or returns long strings as a LiteralBlockScalar"""
    try:
        json_data = json.loads(string_value)
        return LiteralBlockScalar(json.dumps(json_data, indent=2))
    except (ValueError, TypeError):
        if len(string_value) > 80:
            return LiteralBlockScalar(string_value)
    return string_value


def convert_body_to_literal(data):
    """Searches the data for body strings, attempting to pretty-print JSON"""
    if isinstance(data, dict):
        for key, value in data.items():
            # Handle response body case (e.g., response.body.string)
            if key == "body" and isinstance(value, dict) and "string" in value:
                value["string"] = process_string_value(value["string"])

            # Handle request body case (e.g., request.body)
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
    vcr.register_serializer("yaml", PrettyPrintJSONBody)
    return vcr


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _copy_signature(
    func_type: Callable[_P, _R],
) -> Callable[
    [Callable[..., Any]], Callable[Concatenate[GenerativeModel, _P], _R]
]:
    return lambda func: func


# Type annotation for fixture to make LSP work properly
class GenerateContentFixture(Protocol):
    @_copy_signature(GenerativeModel.generate_content)
    def __call__(self): ...


@pytest.fixture(
    name="generate_content",
    params=(
        pytest.param(False, id="sync"),
        pytest.param(True, id="async"),
    ),
)
def fixture_generate_content(
    request: pytest.FixtureRequest,
    vcr: VCR,
) -> Generator[GenerateContentFixture, None, None]:
    """This fixture parameterizes tests that use it to test calling both
    GenerativeModel.generate_content() and GenerativeModel.generate_content_async().
    """
    is_async: bool = request.param

    if is_async:
        # See
        # https://github.com/googleapis/python-aiplatform/blob/cb0e5fedbf45cb0531c0b8611fb7fabdd1f57e56/google/cloud/aiplatform/initializer.py#L717-L729
        _set_async_rest_credentials(credentials=AsyncAnonymousCredentials())

    def wrapper(model: GenerativeModel, *args, **kwargs) -> None:
        if is_async:
            return asyncio.run(model.generate_content_async(*args, **kwargs))
        return model.generate_content(*args, **kwargs)

    with vcr.use_cassette(
        request.node.originalname, allow_playback_repeats=True
    ):
        yield wrapper
