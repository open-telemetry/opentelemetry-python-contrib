# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from importlib.metadata import EntryPoint, entry_points

import pytest

from opentelemetry.instrumentation import openai_v2
from opentelemetry.instrumentation.auto_instrumentation import _load
from opentelemetry.instrumentation.distro import DefaultDistro
from opentelemetry.instrumentation.genai.openai import (
    OpenAIInstrumentor as GenAIOpenAIInstrumentor,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

from .test_utils import (
    DEFAULT_MODEL,
    USER_ONLY_PROMPT,
    V2_SCOPE,
    wrapped_by_genai_openai,
    wrapped_by_v2,
)

pytestmark = pytest.mark.usefixtures("reset_instrumentors")


def _openai_entry_points() -> dict[str, EntryPoint]:
    return {ep.dist.name: ep for ep in entry_points(group="opentelemetry_instrumentor") if ep.name == "openai"}


def test_v2_first_blocks_genai_openai(tracer_provider, caplog):
    caplog.set_level(logging.WARNING, logger=openai_v2.__name__)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    genai_openai = GenAIOpenAIInstrumentor()
    genai_openai.instrument(tracer_provider=tracer_provider)

    assert not genai_openai.is_instrumented_by_opentelemetry
    assert "opentelemetry-instrumentation-genai-openai is disabled" in caplog.text
    assert wrapped_by_v2()


def test_genai_openai_first_is_uninstrumented(tracer_provider):
    genai_openai = GenAIOpenAIInstrumentor()
    genai_openai.instrument(tracer_provider=tracer_provider)
    assert wrapped_by_genai_openai()

    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    assert not genai_openai.is_instrumented_by_opentelemetry
    assert wrapped_by_v2()


@pytest.mark.parametrize(
    "dist_order",
    [
        ("opentelemetry-instrumentation-openai-v2", "opentelemetry-instrumentation-genai-openai"),
        ("opentelemetry-instrumentation-genai-openai", "opentelemetry-instrumentation-openai-v2"),
    ],
    ids=["v2_first", "genai_openai_first"],
)
def test_auto_instrumentation_only_v2_active(monkeypatch, dist_order):
    openai_eps = _openai_entry_points()
    ordered = [openai_eps[name] for name in dist_order]

    def fake_entry_points(group: str, **_: object) -> list[EntryPoint]:
        return ordered if group == "opentelemetry_instrumentor" else []

    monkeypatch.setattr(_load, "entry_points", fake_entry_points)

    _load._load_instrumentors(DefaultDistro())

    assert OpenAIInstrumentor().is_instrumented_by_opentelemetry
    assert not GenAIOpenAIInstrumentor().is_instrumented_by_opentelemetry
    assert wrapped_by_v2()


def test_stray_genai_openai_uninstrument_keeps_v2(tracer_provider):
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    GenAIOpenAIInstrumentor().uninstrument()

    assert wrapped_by_v2()


def test_v2_uninstrument_lifts_block(tracer_provider):
    v2 = OpenAIInstrumentor()
    v2.instrument(tracer_provider=tracer_provider)
    v2.uninstrument()

    genai_openai = GenAIOpenAIInstrumentor()
    genai_openai.instrument(tracer_provider=tracer_provider)

    assert genai_openai.is_instrumented_by_opentelemetry
    assert wrapped_by_genai_openai()


def test_legacy_chat_completion_uses_v2_scope(span_exporter, openai_client, tracer_provider, vcr):
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    with vcr.use_cassette("test_chat_completion_no_content.yaml"):
        openai_client.chat.completions.create(messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, stream=False)

    (span,) = span_exporter.get_finished_spans()
    assert span.instrumentation_scope.name == V2_SCOPE
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert GenAIAttributes.GEN_AI_PROVIDER_NAME not in span.attributes
