# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from django.conf import settings
from django.http import HttpResponse

if not settings.configured:
    settings.configure(
        ROOT_URLCONF=__name__,
        DATABASES={"default": {}},
        MIDDLEWARE=[],
        ALLOWED_HOSTS=["testserver"],
    )

from django.urls import re_path  # noqa: E402

from opentelemetry.instrumentation.django import DjangoInstrumentor  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)


def _simple_view(request):
    return HttpResponse("OK")


urlpatterns = [re_path(r"^traced/", _simple_view)]


@pytest.fixture(name="django_client")
def _django_client_fixture():
    from django.test.client import Client

    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    meter_provider = MeterProvider()
    DjangoInstrumentor().instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    client = Client()
    yield client
    DjangoInstrumentor().uninstrument()


def test_middleware_full_request(benchmark, django_client):
    benchmark(django_client.get, "/traced/")
