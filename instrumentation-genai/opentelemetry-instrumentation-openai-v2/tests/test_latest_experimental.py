# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

import pytest

from opentelemetry.instrumentation import openai_v2
from opentelemetry.instrumentation._semconv import OTEL_SEMCONV_STABILITY_OPT_IN
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

from .test_utils import not_wrapped

pytestmark = pytest.mark.usefixtures("latest_experimental")


@pytest.fixture(name="latest_experimental")
def fixture_latest_experimental(monkeypatch: pytest.MonkeyPatch, reset_instrumentors: None) -> None:
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, "gen_ai_latest_experimental")


def test_latest_experimental_disables_instrumentation(tracer_provider, caplog):
    caplog.set_level(logging.WARNING, logger=openai_v2.__name__)

    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    assert not_wrapped()
    assert "opentelemetry-instrumentation-genai-openai" in caplog.text

    instrumentor.uninstrument()
    assert not instrumentor.is_instrumented_by_opentelemetry
