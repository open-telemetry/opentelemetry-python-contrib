# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Direct-wrapper unit tests for the Agno instrumentation.

Agno's ``Agent.run`` requires a live model, so these tests exercise the traced
wrappers directly with fake ``instance``/``wrapped`` doubles instead of hitting
the network. A separate test verifies that ``AgnoInstrumentor`` actually wraps
and unwraps the real Agno callables.
"""

from __future__ import annotations

import asyncio
import types

import agno.agent
import agno.tools
import pytest

from opentelemetry.instrumentation.agno import AgnoInstrumentor
from opentelemetry.instrumentation.agno.patch import (
    agent_arun,
    agent_run,
    function_call_execute,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode


def _fake_agent():
    return types.SimpleNamespace(
        name="my-agent",
        model=types.SimpleNamespace(id="gpt-4o"),
    )


def _fake_function_call(name="get_weather"):
    return types.SimpleNamespace(
        function=types.SimpleNamespace(name=name),
    )


class _Boom(RuntimeError):
    pass


# --- Agent.run (sync) ------------------------------------------------------


def test_agent_run_success(handler, span_exporter):
    wrapper = agent_run(handler)

    def wrapped(*args, **kwargs):
        return "the answer"

    result = wrapper(wrapped, _fake_agent(), ("hello",), {})

    assert result == "the answer"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent my-agent"
    attrs = span.attributes
    assert (
        attrs[GenAI.GEN_AI_OPERATION_NAME]
        == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
    )
    assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "invoke_agent"
    agent_name = attrs[GenAI.GEN_AI_AGENT_NAME]
    assert agent_name == "my-agent"
    assert isinstance(agent_name, str)
    assert attrs[GenAI.GEN_AI_PROVIDER_NAME] == "agno"
    assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o"
    assert span.status.status_code != StatusCode.ERROR


def test_agent_run_error(handler, span_exporter):
    wrapper = agent_run(handler)

    def wrapped(*args, **kwargs):
        raise _Boom("kaboom")

    with pytest.raises(_Boom, match="kaboom"):
        wrapper(wrapped, _fake_agent(), ("hello",), {})

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[error_attributes.ERROR_TYPE] == "_Boom"
    assert span.status.status_code == StatusCode.ERROR
    # agent attributes are still present on the failed span
    assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "my-agent"
    assert span.attributes[GenAI.GEN_AI_PROVIDER_NAME] == "agno"


def test_agent_run_missing_model(handler, span_exporter):
    wrapper = agent_run(handler)
    instance = types.SimpleNamespace(name="my-agent", model=None)

    wrapper(lambda *a, **k: "ok", instance, (), {})

    span = span_exporter.get_finished_spans()[0]
    assert GenAI.GEN_AI_REQUEST_MODEL not in span.attributes
    assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "my-agent"


# --- Agent.arun (async) ----------------------------------------------------


def test_agent_arun_success(handler, span_exporter):
    wrapper = agent_arun(handler)

    async def wrapped(*args, **kwargs):
        return "async answer"

    result = asyncio.run(wrapper(wrapped, _fake_agent(), ("hi",), {}))

    assert result == "async answer"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent my-agent"
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "invoke_agent"
    assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "my-agent"
    assert span.attributes[GenAI.GEN_AI_PROVIDER_NAME] == "agno"
    assert span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o"
    assert span.status.status_code != StatusCode.ERROR


def test_agent_arun_error(handler, span_exporter):
    wrapper = agent_arun(handler)

    async def wrapped(*args, **kwargs):
        raise _Boom("async boom")

    with pytest.raises(_Boom, match="async boom"):
        asyncio.run(wrapper(wrapped, _fake_agent(), (), {}))

    span = span_exporter.get_finished_spans()[0]
    assert span.attributes[error_attributes.ERROR_TYPE] == "_Boom"
    assert span.status.status_code == StatusCode.ERROR


# --- FunctionCall.execute (tool) -------------------------------------------


def test_tool_execute_success(handler, span_exporter):
    wrapper = function_call_execute(handler)

    def wrapped(*args, **kwargs):
        return "sunny"

    result = wrapper(wrapped, _fake_function_call(), (), {})

    assert result == "sunny"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "execute_tool get_weather"
    assert (
        span.attributes[GenAI.GEN_AI_OPERATION_NAME]
        == GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
    )
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"
    tool_name = span.attributes[GenAI.GEN_AI_TOOL_NAME]
    assert tool_name == "get_weather"
    assert isinstance(tool_name, str)
    tool_result = span.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT]
    assert tool_result == "sunny"
    assert isinstance(tool_result, str)
    assert span.status.status_code != StatusCode.ERROR


def test_tool_execute_error(handler, span_exporter):
    wrapper = function_call_execute(handler)

    def wrapped(*args, **kwargs):
        raise _Boom("tool failed")

    with pytest.raises(_Boom, match="tool failed"):
        wrapper(wrapped, _fake_function_call(), (), {})

    span = span_exporter.get_finished_spans()[0]
    assert span.name == "execute_tool get_weather"
    assert span.attributes[GenAI.GEN_AI_TOOL_NAME] == "get_weather"
    assert span.attributes[error_attributes.ERROR_TYPE] == "_Boom"
    assert span.status.status_code == StatusCode.ERROR


def test_tool_execute_missing_name(handler, span_exporter):
    wrapper = function_call_execute(handler)
    instance = types.SimpleNamespace(function=None)

    wrapper(lambda *a, **k: "ok", instance, (), {})

    span = span_exporter.get_finished_spans()[0]
    assert span.attributes[GenAI.GEN_AI_TOOL_NAME] == "unknown"


# --- instrument / uninstrument round-trip ----------------------------------


def test_instrument_wraps_and_unwraps():
    instrumentor = AgnoInstrumentor()
    instrumentor.instrument()
    try:
        assert hasattr(agno.agent.Agent.run, "__wrapped__")
        assert hasattr(agno.agent.Agent.arun, "__wrapped__")
        assert hasattr(agno.tools.FunctionCall.execute, "__wrapped__")
    finally:
        instrumentor.uninstrument()

    assert not hasattr(agno.agent.Agent.run, "__wrapped__")
    assert not hasattr(agno.agent.Agent.arun, "__wrapped__")
    assert not hasattr(agno.tools.FunctionCall.execute, "__wrapped__")
