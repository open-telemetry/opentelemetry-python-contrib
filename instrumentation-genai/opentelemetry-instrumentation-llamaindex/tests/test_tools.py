# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""End-to-end tests for LlamaIndex ``FunctionTool`` instrumentation.

A ``FunctionTool`` runs a plain Python callable locally, so these tests exercise
the full instrumentation path without any LLM or network access.
"""

import asyncio

import pytest
from llama_index.core.tools.function_tool import FunctionTool

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

_EXECUTE_TOOL = GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value


def _double_tool() -> FunctionTool:
    return FunctionTool.from_defaults(fn=lambda x: x * 2, name="double")


def _raising_tool() -> FunctionTool:
    def boom(x):
        raise ValueError("tool failed")

    return FunctionTool.from_defaults(fn=boom, name="boom")


def test_call_emits_tool_span(span_exporter, instrument):
    tool = _double_tool()

    result = tool.call(3)

    assert result.raw_output == 6

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"{_EXECUTE_TOOL} double"
    assert span.kind == SpanKind.CLIENT
    assert span.status.status_code == StatusCode.UNSET

    operation = span.attributes[GenAI.GEN_AI_OPERATION_NAME]
    assert operation == _EXECUTE_TOOL
    assert isinstance(operation, str)

    tool_name = span.attributes[GenAI.GEN_AI_TOOL_NAME]
    assert tool_name == "double"
    assert isinstance(tool_name, str)

    tool_type = span.attributes[GenAI.GEN_AI_TOOL_TYPE]
    assert tool_type == "function"
    assert isinstance(tool_type, str)


def test_acall_emits_tool_span(span_exporter, instrument):
    tool = _double_tool()

    result = asyncio.run(tool.acall(3))

    assert result.raw_output == 6

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"{_EXECUTE_TOOL} double"
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == _EXECUTE_TOOL
    assert span.attributes[GenAI.GEN_AI_TOOL_NAME] == "double"
    assert span.status.status_code == StatusCode.UNSET


def test_call_captures_content(span_exporter, instrument_with_content):
    tool = _double_tool()

    result = tool.call(3)

    assert result.raw_output == 6

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    arguments = span.attributes[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS]
    assert isinstance(arguments, str)
    assert "3" in arguments

    tool_result = span.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT]
    assert tool_result == "6"
    assert isinstance(tool_result, str)


def test_call_with_unserializable_argument_does_not_raise(
    span_exporter, instrument_with_content
):
    # An argument the GenAI JSON encoder cannot serialize must not make the
    # instrumentation raise out of the user's tool call.
    class _Unserializable:
        pass

    tool = FunctionTool.from_defaults(fn=lambda obj: "ok", name="echo")

    result = tool.call(_Unserializable())

    assert result.raw_output == "ok"
    span = span_exporter.get_finished_spans()[0]
    arguments = span.attributes[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS]
    assert isinstance(arguments, str)


def test_call_omits_content_by_default(span_exporter, instrument):
    tool = _double_tool()

    tool.call(3)

    span = span_exporter.get_finished_spans()[0]
    assert GenAI.GEN_AI_TOOL_CALL_ARGUMENTS not in span.attributes
    assert GenAI.GEN_AI_TOOL_CALL_RESULT not in span.attributes


def test_call_error_records_span_and_reraises(span_exporter, instrument):
    tool = _raising_tool()

    with pytest.raises(ValueError, match="tool failed"):
        tool.call(3)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.status.status_code == StatusCode.ERROR
    error_type = span.attributes["error.type"]
    assert error_type == "ValueError"
    assert isinstance(error_type, str)
    assert span.attributes[GenAI.GEN_AI_TOOL_NAME] == "boom"


def test_acall_error_records_span_and_reraises(span_exporter, instrument):
    tool = _raising_tool()

    with pytest.raises(ValueError, match="tool failed"):
        asyncio.run(tool.acall(3))

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "ValueError"


def test_instrument_wraps_and_uninstrument_unwraps(span_exporter, instrument):
    # While instrumented, FunctionTool.call/acall are wrapped and emit a span.
    call_wrapper = FunctionTool.__dict__["call"]
    acall_wrapper = FunctionTool.__dict__["acall"]
    assert call_wrapper.__wrapped__ is not None
    assert acall_wrapper.__wrapped__ is not None

    _double_tool().call(3)
    assert len(span_exporter.get_finished_spans()) == 1

    instrument.uninstrument()

    # Our wrapper layer is removed (the __dict__ entry changed identity).
    assert FunctionTool.__dict__["call"] is not call_wrapper
    assert FunctionTool.__dict__["acall"] is not acall_wrapper

    # After uninstrument, calling the tool emits no additional span.
    span_exporter.clear()
    _double_tool().call(3)
    assert span_exporter.get_finished_spans() == ()

    # Re-instrument so the conftest fixture teardown (uninstrument) stays valid.
    instrument.instrument()
