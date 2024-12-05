"""Unit tests configuration module."""

import re
from typing import Any, Mapping, MutableMapping

import pytest
import vertexai
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
