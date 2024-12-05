"""Unit tests configuration module."""

from os import replace
import re
from typing import Any, Mapping, MutableMapping

import pytest
from google.auth.credentials import AnonymousCredentials

from opentelemetry import trace
from opentelemetry.instrumentation.vertexai_v2 import VertexAIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

pytest_plugins = []

import vertexai
from vcr import VCR
from vcr.record_mode import RecordMode
from vcr.request import Request


@pytest.fixture(scope="session")
def exporter():
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)

    provider = TracerProvider()
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    VertexAIInstrumentor().instrument()

    return exporter


@pytest.fixture(autouse=True)
def clear_exporter(exporter):
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
    if vcr.record_mode is RecordMode.NONE:
        vertexai.init(credentials=AnonymousCredentials())
    else:
        vertexai.init()


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
            r"/projects/[^/]+/", f"/projects/fake-project/", request.uri
        )
        return request

    def before_response_cb(response: MutableMapping[str, Any]):
        response["headers"] = filter_headers(response["headers"])
        return response

    return {
        "before_record_request": before_record_cb,
        "before_record_response": before_response_cb,
        "ignore_hosts": ["oauth2.googleapis.com"],
    }
