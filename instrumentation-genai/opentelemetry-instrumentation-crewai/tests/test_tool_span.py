# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from opentelemetry.instrumentation.crewai._wrappers import wrap_tool_run
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode

from .conftest import fake_tool


def test_tool_span_has_tool_name(handler_and_exporter):
    handler, exporter = handler_and_exporter
    tool = fake_tool(name="word_count")
    wrapper = wrap_tool_run(handler)

    result = wrapper(
        lambda *a, **k: "42 words", tool, (), {"text": "hello world"}
    )

    assert result == "42 words"
    (span,) = exporter.get_finished_spans()
    assert span.name == "execute_tool word_count"
    assert span.attributes[gen_ai_attributes.GEN_AI_TOOL_NAME] == "word_count"
    assert gen_ai_attributes.GEN_AI_TOOL_CALL_ARGUMENTS not in span.attributes
    assert gen_ai_attributes.GEN_AI_TOOL_CALL_RESULT not in span.attributes


def test_tool_span_captures_arguments_and_result_when_flag_enabled(
    content_capturing_handler_and_exporter,
):
    handler, exporter = content_capturing_handler_and_exporter
    tool = fake_tool(name="word_count")
    wrapper = wrap_tool_run(handler)

    wrapper(lambda *a, **k: "42 words", tool, (), {"text": "hello world"})

    (span,) = exporter.get_finished_spans()
    assert (
        "hello world"
        in span.attributes[gen_ai_attributes.GEN_AI_TOOL_CALL_ARGUMENTS]
    )
    assert (
        span.attributes[gen_ai_attributes.GEN_AI_TOOL_CALL_RESULT]
        == '"42 words"'
    )


def test_tool_span_records_exception_and_reraises(handler_and_exporter):
    handler, exporter = handler_and_exporter
    tool = fake_tool()
    wrapper = wrap_tool_run(handler)

    def wrapped(*args, **kwargs):
        raise ValueError("bad tool input")

    with pytest.raises(ValueError, match="bad tool input"):
        wrapper(wrapped, tool, (), {})

    (span,) = exporter.get_finished_spans()
    assert span.name == "execute_tool word_count"
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[error_attributes.ERROR_TYPE] == "ValueError"
