# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import pytest
import requests
from requests.adapters import BaseAdapter
from requests.models import Response

from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

_URL = "http://mock/status/200"


class _FakeAdapter(BaseAdapter):
    def __init__(self):
        super().__init__()
        resp = Response()
        resp.status_code = 200
        self._response = resp

    def send(self, *args, **kwargs):
        return self._response

    def close(self):
        pass


@pytest.fixture
def instrumented_session():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    RequestsInstrumentor().instrument(tracer_provider=provider)
    session = requests.Session()
    session.mount("http://", _FakeAdapter())
    yield session
    RequestsInstrumentor().uninstrument()


def test_instrumented_send(benchmark, instrumented_session):
    benchmark(instrumented_session.get, _URL)
