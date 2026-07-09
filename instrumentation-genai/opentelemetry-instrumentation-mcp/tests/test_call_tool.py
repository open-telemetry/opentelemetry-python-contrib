# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline unit tests for the MCP ``call_tool`` instrumentation.

These tests drive the traced async wrapper directly with a fake MCP
``ClientSession`` instance and a fake async ``wrapped`` callable, so no MCP
server is required.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.types import CallToolResult, TextContent

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.mcp.patch import call_tool
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler


def _make_result(text: str = "sunny") -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=False,
    )


def _fake_instance() -> Any:
    # A bare ClientSession without running __init__ is enough for the wrapper,
    # which never touches ``instance``.
    return ClientSession.__new__(ClientSession)


def _run_success(
    handler: TelemetryHandler,
    *,
    name: str = "get_weather",
    arguments: Any = None,
    result: CallToolResult | None = None,
) -> CallToolResult:
    wrapper = call_tool(handler)
    canned = result if result is not None else _make_result()

    async def wrapped(*args: Any, **kwargs: Any) -> CallToolResult:
        return canned

    async def drive() -> CallToolResult:
        return await wrapper(
            wrapped,
            _fake_instance(),
            (name, arguments) if arguments is not None else (name,),
            {},
        )

    return asyncio.run(drive())


# --- span emission: success path ------------------------------------------


def test_call_tool_emits_execute_tool_span(span_exporter, tracer_provider):
    handler = TelemetryHandler(tracer_provider=tracer_provider)

    returned = _run_success(handler, name="get_weather")

    assert isinstance(returned, CallToolResult)
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == "execute_tool get_weather"

    op = span.attributes[GenAI.GEN_AI_OPERATION_NAME]
    assert op == GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
    assert op == "execute_tool"
    assert isinstance(op, str)

    tool_name = span.attributes[GenAI.GEN_AI_TOOL_NAME]
    assert tool_name == "get_weather"
    assert isinstance(tool_name, str)

    assert span.status.status_code is StatusCode.UNSET
    # arguments must not be captured when content capture is off
    assert GenAI.GEN_AI_TOOL_CALL_ARGUMENTS not in span.attributes


def test_call_tool_captures_arguments_when_content_enabled(
    span_exporter, tracer_provider, monkeypatch
):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "span_only"
    )
    # Reset the process-wide semconv stability singleton so the experimental
    # opt-in above takes effect, then reset it again on teardown so this global
    # state does not leak into other tests.
    _OpenTelemetrySemanticConventionStability._initialized = False
    _OpenTelemetrySemanticConventionStability._initialize()
    monkeypatch.setattr(
        _OpenTelemetrySemanticConventionStability,
        "_initialized",
        False,
        raising=False,
    )

    handler = TelemetryHandler(tracer_provider=tracer_provider)
    assert handler.should_capture_content() is True

    _run_success(handler, name="get_weather", arguments={"city": "London"})

    span = span_exporter.get_finished_spans()[0]
    args_attr = span.attributes[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS]
    assert isinstance(args_attr, str)
    assert args_attr == '{"city":"London"}'

    result_attr = span.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT]
    assert isinstance(result_attr, str)
    assert "sunny" in result_attr


# --- span emission: error path --------------------------------------------


class _ToolBoom(Exception):
    pass


def test_call_tool_error_path_records_error_and_reraises(
    span_exporter, tracer_provider
):
    handler = TelemetryHandler(tracer_provider=tracer_provider)
    wrapper = call_tool(handler)

    raised = _ToolBoom("kaboom")

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        raise raised

    async def drive() -> Any:
        return await wrapper(wrapped, _fake_instance(), ("get_weather",), {})

    with pytest.raises(_ToolBoom) as exc_info:
        asyncio.run(drive())

    # original exception re-raised unmodified
    assert exc_info.value is raised

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.status.status_code is StatusCode.ERROR
    error_type = span.attributes[error_attributes.ERROR_TYPE]
    assert error_type == "_ToolBoom"
    assert isinstance(error_type, str)
    assert span.attributes[GenAI.GEN_AI_TOOL_NAME] == "get_weather"


# --- name resolution via kwargs -------------------------------------------


def test_call_tool_reads_name_from_kwargs(span_exporter, tracer_provider):
    handler = TelemetryHandler(tracer_provider=tracer_provider)
    wrapper = call_tool(handler)

    async def wrapped(*args: Any, **kwargs: Any) -> CallToolResult:
        return _make_result()

    async def drive() -> Any:
        return await wrapper(
            wrapped, _fake_instance(), (), {"name": "kw_tool"}
        )

    asyncio.run(drive())

    span = span_exporter.get_finished_spans()[0]
    assert span.attributes[GenAI.GEN_AI_TOOL_NAME] == "kw_tool"
    assert span.name == "execute_tool kw_tool"


# --- instrument / uninstrument wraps and unwraps call_tool ----------------


def test_instrument_wraps_and_uninstrument_unwraps(instrument):
    assert hasattr(ClientSession.call_tool, "__wrapped__")

    instrument.uninstrument()
    assert not hasattr(ClientSession.call_tool, "__wrapped__")

    # re-instrument so the conftest fixture teardown's uninstrument is a no-op
    # against an already-unwrapped method (uninstrument is idempotent-safe).
    instrument.instrument(tracer_provider=None)
    assert hasattr(ClientSession.call_tool, "__wrapped__")
