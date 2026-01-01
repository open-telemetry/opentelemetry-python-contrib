"""Unit tests configuration module."""

import json
import os

import pytest
import yaml

try:
    import boto3
    from langchain_aws import ChatBedrock
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI
    HAS_LANGCHAIN_DEPS = True
except ImportError:
    HAS_LANGCHAIN_DEPS = False
    boto3 = None  # type: ignore
    ChatBedrock = None  # type: ignore
    ChatGoogleGenerativeAI = None  # type: ignore
    ChatOpenAI = None  # type: ignore

try:
    from opentelemetry.instrumentation.langchain import LangChainInstrumentor
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False
    LangChainInstrumentor = None  # type: ignore

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function", name="chat_openai_gpt_3_5_turbo_model")
def fixture_chat_openai_gpt_3_5_turbo_model():
    if not HAS_LANGCHAIN_DEPS:
        pytest.skip("langchain dependencies not installed")
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        max_tokens=100,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        stop_sequences=["\n", "Human:", "AI:"],
        seed=100,
    )
    yield llm


@pytest.fixture(scope="function", name="us_amazon_nova_lite_v1_0")
def fixture_us_amazon_nova_lite_v1_0():
    if not HAS_LANGCHAIN_DEPS:
        pytest.skip("langchain dependencies not installed")
    llm_model_value = "us.amazon.nova-lite-v1:0"
    llm = ChatBedrock(
        model_id=llm_model_value,
        client=boto3.client(
            "bedrock-runtime",
            aws_access_key_id="test_key",
            aws_secret_access_key="test_secret",
            region_name="us-west-2",
            aws_account_id="test_account",
        ),
        provider="amazon",
        temperature=0.1,
        max_tokens=100,
    )
    yield llm


@pytest.fixture(scope="function", name="gemini")
def fixture_gemini():
    if not HAS_LANGCHAIN_DEPS:
        pytest.skip("langchain dependencies not installed")
    llm_model_value = "gemini-2.5-pro"
    llm = ChatGoogleGenerativeAI(model=llm_model_value, api_key="test_key")
    yield llm


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function")
def start_instrumentation(
    tracer_provider,
):
    if not HAS_LANGCHAIN:
        pytest.skip("langchain not installed")
    instrumentor = LangChainInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
    )

    yield instrumentor
    instrumentor.uninstrument()


@pytest.fixture(autouse=True)
def environment():
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "test_openai_api_key"


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [
            ("cookie", "test_cookie"),
            ("authorization", "Bearer test_openai_api_key"),
            ("openai-organization", "test_openai_org_id"),
            ("openai-project", "test_openai_project_id"),
        ],
        "decode_compressed_response": True,
        "before_record_response": scrub_response_headers,
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


def scrub_response_headers(response):
    """
    This scrubs sensitive response headers. Note they are case-sensitive!
    """
    response["headers"]["openai-organization"] = "test_openai_org_id"
    response["headers"]["Set-Cookie"] = "test_set_cookie"
    return response
