# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
from functools import wraps

import pytest

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT ", "6379"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"
BROKER_URL = f"{REDIS_URL}/0"
BACKEND_URL = f"{REDIS_URL}/1"


@pytest.fixture(scope="session")
def celery_config():
    return {"broker_url": BROKER_URL, "result_backend": BACKEND_URL}


@pytest.fixture
def celery_worker_parameters():
    return {
        # See https://github.com/celery/celery/issues/3642#issuecomment-457773294
        "perform_ping_check": False,
    }


@pytest.fixture(autouse=True)
def patch_celery_app(celery_app, celery_worker):
    """Patch task decorator on app fixture to reload worker"""

    # See https://github.com/celery/celery/issues/3642
    def wrap_task(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            celery_worker.reload()
            return result

        return wrapper

    celery_app.task = wrap_task(celery_app.task)


@pytest.fixture(autouse=True)
def instrument(tracer_provider, memory_exporter):
    CeleryInstrumentor().instrument(tracer_provider=tracer_provider)
    memory_exporter.clear()

    yield

    CeleryInstrumentor().uninstrument()


@pytest.fixture(scope="function")
def tracer_provider(memory_exporter):
    original_tracer_provider = trace_api.get_tracer_provider()

    tracer_provider = TracerProvider()

    span_processor = export.SimpleSpanProcessor(memory_exporter)
    tracer_provider.add_span_processor(span_processor)

    trace_api.set_tracer_provider(tracer_provider)

    yield tracer_provider

    trace_api.set_tracer_provider(original_tracer_provider)


@pytest.fixture(scope="function")
def memory_exporter():
    memory_exporter = InMemorySpanExporter()
    return memory_exporter
