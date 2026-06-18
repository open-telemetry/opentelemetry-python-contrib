# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import pytest
import urllib3
from mocket import Mocketizer
from mocket.mocks.mockhttp import Entry

from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

_URL = "http://mock/status/200"


@pytest.fixture
def instrumented_pool():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    URLLib3Instrumentor().instrument(tracer_provider=provider)
    pool = urllib3.HTTPConnectionPool("mock", port=80)
    with Mocketizer():
        Entry.single_register(
            Entry.GET, _URL, body="Hello!", match_querystring=False
        )
        yield pool
    URLLib3Instrumentor().uninstrument()


def test_instrumented_urlopen(benchmark, instrumented_pool):
    def run():
        Entry.single_register(
            Entry.GET, _URL, body="Hello!", match_querystring=False
        )
        instrumented_pool.urlopen("GET", "/status/200")

    benchmark(run)
