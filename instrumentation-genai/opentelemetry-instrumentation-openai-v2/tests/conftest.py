"""Unit tests configuration module."""

import json
import os

import pytest
import yaml
from openai import AsyncOpenAI, OpenAI

from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.instrumentation.openai_v2.utils import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
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
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogExporter()
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
    meter_provider = MeterProvider(
        metric_readers=[metric_reader],
    )

    return meter_provider


@pytest.fixture(autouse=True)
def environment():
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "test_openai_api_key"


@pytest.fixture
def openai_client():
    return OpenAI()


@pytest.fixture
def async_openai_client():
    return AsyncOpenAI()


@pytest.fixture(scope="module")
def vcr_config():
    def comprehensive_scrubber(response):
        """Apply all scrubbing functions to clean sensitive data"""
        response = scrub_response_headers(response)
        response = scrub_response_body(response)
        return response
    
    def request_scrubber(request):
        """Scrub request data including URI paths"""
        request = scrub_request_body(request)
        request = scrub_request_uri(request)
        return request
    
    return {
        "filter_headers": [
            ("cookie", "test_cookie"),
            ("authorization", "Bearer test_openai_api_key"),
            ("openai-organization", "test_openai_org_id"),
            ("openai-project", "test_openai_project_id"),
        ],
        "decode_compressed_response": True,
        "before_record_response": comprehensive_scrubber,
        "before_record_request": request_scrubber,
    }


@pytest.fixture(scope="function")
def instrument_no_content(tracer_provider, logger_provider, meter_provider):
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "False"}
    )

    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(tracer_provider, logger_provider, meter_provider):
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "True"}
    )
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content_unsampled(
    span_exporter, logger_provider, meter_provider
):
    os.environ.update(
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "True"}
    )

    tracer_provider = TracerProvider(sampler=ALWAYS_OFF)
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


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


def scrub_response_headers(response):
    """
    This scrubs sensitive response headers. Note they are case-sensitive!
    """
    response["headers"]["openai-organization"] = "test_openai_org_id"
    response["headers"]["openai-project"] = "test_openai_project_id"
    response["headers"]["Set-Cookie"] = "test_set_cookie"
    response["headers"]["x-request-id"] = "test_request_id"
    
    # Scrub CloudFlare and timing headers that could be used for tracking
    if "CF-RAY" in response["headers"]:
        response["headers"]["CF-RAY"] = "test_cf_ray_id-ATL"
    if "Date" in response["headers"]:
        response["headers"]["Date"] = "Mon, 01 Jan 2024 00:00:00 GMT"
    if "openai-processing-ms" in response["headers"]:
        response["headers"]["openai-processing-ms"] = "100"
    if "x-envoy-upstream-service-time" in response["headers"]:
        response["headers"]["x-envoy-upstream-service-time"] = "100"
    
    # Scrub rate limiting headers that contain timing info
    rate_limit_headers = [
        "x-ratelimit-limit-requests", "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens", 
        "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"
    ]
    for header in rate_limit_headers:
        if header in response["headers"]:
            if "limit" in header:
                response["headers"][header] = "1000"
            elif "remaining" in header:
                response["headers"][header] = "999"  
            elif "reset" in header:
                response["headers"][header] = "1s"
        
    return response


def scrub_response_body(response):
    """
    Scrub sensitive data from response body content including conversation IDs,
    response IDs, message IDs, and other identifiers that aren't needed for testing.
    """
    import re
    
    if "body" not in response or "string" not in response["body"]:
        return response
    
    try:
        # Parse the JSON response body
        body_content = json.loads(response["body"]["string"])
        
        # Scrub various OpenAI IDs (e.g., "conv_abc123" -> "test_conversation_id")
        if "id" in body_content and isinstance(body_content["id"], str):
            if body_content["id"].startswith("conv_"):
                body_content["id"] = "test_conversation_id"
            elif body_content["id"].startswith("resp_"):
                body_content["id"] = "test_response_id"
            elif body_content["id"].startswith("msg_"):
                body_content["id"] = "test_message_id"
            elif body_content["id"].startswith("req_"):
                body_content["id"] = "test_request_id"
        
        # Scrub message IDs in output array (for responses API)
        if "output" in body_content and isinstance(body_content["output"], list):
            for output_item in body_content["output"]:
                if isinstance(output_item, dict) and "id" in output_item:
                    if output_item["id"].startswith("msg_"):
                        output_item["id"] = "test_message_id"
        
        # Scrub conversation items (for conversation items list)
        if "data" in body_content and isinstance(body_content["data"], list):
            for item in body_content["data"]:
                if isinstance(item, dict) and "id" in item:
                    if item["id"].startswith("msg_"):
                        item["id"] = "test_message_id"
                    elif item["id"].startswith("conv_"):
                        item["id"] = "test_conversation_id"
        
        # Scrub pagination IDs (first_id, last_id)
        for id_field in ["first_id", "last_id"]:
            if id_field in body_content and isinstance(body_content[id_field], str):
                if body_content[id_field].startswith("msg_"):
                    body_content[id_field] = "test_message_id"
                elif body_content[id_field].startswith("conv_"):
                    body_content[id_field] = "test_conversation_id"
        
        # Scrub timestamps to prevent tracking
        if "created_at" in body_content and isinstance(body_content["created_at"], (int, float)):
            body_content["created_at"] = 1234567890
        
        # Scrub billing information
        if "billing" in body_content and isinstance(body_content["billing"], dict):
            if "payer" in body_content["billing"]:
                body_content["billing"]["payer"] = "test_payer"
        
        # Scrub any nested ID references
        def scrub_nested_ids(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == "conversation_id" and isinstance(value, str) and value.startswith("conv_"):
                        obj[key] = "test_conversation_id"
                    elif key == "request_id" and isinstance(value, str) and value.startswith("req_"):
                        obj[key] = "test_request_id"
                    elif key == "id" and isinstance(value, str):
                        if value.startswith("conv_"):
                            obj[key] = "test_conversation_id"
                        elif value.startswith("msg_"):
                            obj[key] = "test_message_id"
                        elif value.startswith("resp_"):
                            obj[key] = "test_response_id"
                        elif value.startswith("req_"):
                            obj[key] = "test_request_id"
                    elif key == "created_at" and isinstance(value, (int, float)):
                        obj[key] = 1234567890
                    elif key == "payer" and isinstance(value, str):
                        obj[key] = "test_payer"
                    elif isinstance(value, (dict, list)):
                        scrub_nested_ids(value)
            elif isinstance(obj, list):
                for item in obj:
                    scrub_nested_ids(item)
        
        scrub_nested_ids(body_content)
        
        # Update the response body with scrubbed content
        response["body"]["string"] = json.dumps(body_content)
        
    except (json.JSONDecodeError, KeyError, TypeError):
        # If we can't parse the JSON or it's not in expected format, skip scrubbing
        pass
    
    return response


def scrub_request_body(request):
    """
    Scrub sensitive data from request body content.
    """
    if not hasattr(request, 'body') or not request.body:
        return request
    
    try:
        # Handle both string and bytes request body
        body_data = request.body
        if isinstance(body_data, bytes):
            body_data = body_data.decode('utf-8')
        
        # Parse the JSON request body
        body_content = json.loads(body_data)
        
        # Scrub conversation IDs in request body
        if "conversation" in body_content and isinstance(body_content["conversation"], str):
            if body_content["conversation"].startswith("conv_"):
                body_content["conversation"] = "test_conversation_id"
        
        # Update the request body with scrubbed content
        request.body = json.dumps(body_content)
        
    except (json.JSONDecodeError, AttributeError, TypeError, UnicodeDecodeError):
        # If we can't parse the JSON or it's not in expected format, skip scrubbing
        pass
    
    return request


def scrub_request_uri(request):
    """
    Scrub sensitive IDs from request URI paths.
    """
    import re
    
    if hasattr(request, 'uri') and request.uri:
        # Replace conversation IDs in URI path
        request.uri = re.sub(r'/conversations/conv_[a-f0-9]+', '/conversations/test_conversation_id', request.uri)
        # Replace message IDs in URI path
        request.uri = re.sub(r'/messages/msg_[a-f0-9]+', '/messages/test_message_id', request.uri)
        # Replace response IDs in URI path
        request.uri = re.sub(r'/responses/resp_[a-f0-9]+', '/responses/test_response_id', request.uri)
    
    return request
