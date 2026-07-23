# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.crewai import _wrappers
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.handler import TelemetryHandler


def _make_handler_and_exporter() -> tuple[
    TelemetryHandler, InMemorySpanExporter
]:
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    handler = TelemetryHandler(tracer_provider=provider)
    return handler, exp


@pytest.fixture
def handler_and_exporter():
    """A TelemetryHandler and its backing InMemorySpanExporter, fresh per
    test, with content capture off (the default)."""
    handler, exp = _make_handler_and_exporter()
    yield handler, exp
    exp.clear()


@pytest.fixture
def content_capturing_handler_and_exporter():
    """Same as ``handler_and_exporter``, but with content capture on.

    Two things have to be true at once for message content (input/output
    messages on inference/agent/workflow invocations) to actually land on a
    span, both verified by reading opentelemetry-util-genai's source rather
    than assumed:

    - ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` has to be a
      real capturing-mode value (``span_only`` here), not just ``true`` --
      ``true`` only satisfies ``TelemetryHandler.should_capture_content()``
      on the legacy path, which gates *whether* our wrappers populate
      ``arguments``/``tool_result``/message fields at all, but says nothing
      about whether the util then puts that content on the span.
    - ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` also has
      to be set, because ``get_content_attributes()`` returns ``{}``
      unconditionally when not in experimental mode, regardless of the
      capture-content setting.

    ``TelemetryHandler`` also reads the capture-content env var once, at
    construction time (not per-call), so both env vars have to be set
    before the handler is built. The stability opt-in itself is cached in
    a module-level singleton the first time it's checked, so that singleton
    has to be reset per test too, or a later test would see whatever mode
    the first test that touched it happened to set.
    """
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = (
        "span_only"
    )
    os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = "gen_ai_latest_experimental"
    _OpenTelemetrySemanticConventionStability._initialized = False
    _OpenTelemetrySemanticConventionStability._initialize()

    handler, exp = _make_handler_and_exporter()
    yield handler, exp
    exp.clear()
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    _OpenTelemetrySemanticConventionStability._initialized = False
    _OpenTelemetrySemanticConventionStability._initialize()


@pytest.fixture(autouse=True)
def _reset_instrumentation_state():
    """Module-level correlation state must not leak between tests."""
    yield
    _wrappers._handoff_spans.clear()
    _wrappers._pending_llm_calls.clear()


def fake_crew(
    *, agents=None, tasks=None, process="sequential", crew_id="crew-1"
):
    return SimpleNamespace(
        id=crew_id,
        agents=agents or [],
        tasks=tasks or [],
        process=SimpleNamespace(value=process),
    )


def fake_task(*, description="do the thing", context=None):
    return SimpleNamespace(description=description, context=context)


def fake_agent(*, role="Researcher", crew=None):
    return SimpleNamespace(role=role, crew=crew)


def fake_llm(*, model="gpt-4o-mini", provider="openai"):
    return SimpleNamespace(model=model, provider=provider)


def fake_tool(*, name="word_count"):
    return SimpleNamespace(name=name)
