"""Unit tests configuration module."""

import json
import re
from typing import Any, Mapping, MutableMapping

import pytest
import vertexai
import yaml
from google.auth.credentials import AnonymousCredentials
from vcr import VCR
from vcr.record_mode import RecordMode
from vcr.request import Request

from opentelemetry import trace
from opentelemetry.instrumentation.vertexai_v2 import VertexAIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

pytest_plugins = []

FAKE_PROJECT = "fake-project"


@pytest.fixture(scope="session")
def exporter():
    span_exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(span_exporter)

    provider = TracerProvider()
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    VertexAIInstrumentor().instrument()

    return span_exporter


@pytest.fixture(autouse=True)
def clear_exporter(exporter):  # pylint: disable=redefined-outer-name
    exporter.clear()


@pytest.fixture(autouse=True)
def vertexai_init(vcr: VCR) -> None:
    # Unfortunately I couldn't find a nice way to globally reset the global_config for each
    # test because different vertex submodules reference the global instance directly
    # https://github.com/googleapis/python-aiplatform/blob/v1.74.0/google/cloud/aiplatform/initializer.py#L687
    # so this config will leak if we don't call init() for each test.

    # When not recording (in CI), don't do any auth. That prevents trying to read application
    # default credentials from the filesystem or metadata server and oauth token exchange. This
    # is not the interesting part of our instrumentation to test.
    print(f"VCR Mode is {vcr.record_mode=}, {RecordMode.NONE}")
    vertex_init_kwargs = {"api_transport": "rest"}
    if vcr.record_mode == RecordMode.NONE:
        vertex_init_kwargs["credentials"] = AnonymousCredentials()
        vertex_init_kwargs["project"] = FAKE_PROJECT
    vertexai.init(**vertex_init_kwargs)


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
            r"/projects/[^/]+/", f"/projects/{FAKE_PROJECT}/", request.uri
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
