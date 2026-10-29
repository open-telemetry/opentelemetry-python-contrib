# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging

from openai.resources.chat.completions import Completions
from wrapt import FunctionWrapper

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor


def test_latest_experimental_disables_instrumentation(monkeypatch, caplog):
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, "gen_ai_latest_experimental")
    _OpenTelemetrySemanticConventionStability._initialized = False
    instrumentor = OpenAIInstrumentor()
    try:
        with caplog.at_level(logging.WARNING, logger="opentelemetry.instrumentation.openai_v2"):
            instrumentor.instrument()

        assert not isinstance(Completions.__dict__["create"], FunctionWrapper)
        assert "opentelemetry-instrumentation-genai-openai" in caplog.text
    finally:
        instrumentor.uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False

    assert not isinstance(Completions.__dict__["create"], FunctionWrapper)
