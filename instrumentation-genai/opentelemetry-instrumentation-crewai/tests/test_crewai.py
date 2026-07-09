# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the CrewAI instrumentation.

``Crew.kickoff`` runs real agents and LLM calls (network), so instead of
exercising the whole crew we drive each traced wrapper directly against fake
``instance`` objects and fake ``wrapped`` callables. This keeps the tests
offline while still asserting the exact telemetry each wrapper emits.
"""

from __future__ import annotations

import types

import pytest

from opentelemetry.instrumentation.crewai import CrewAIInstrumentor
from opentelemetry.instrumentation.crewai.patch import (
    wrap_agent_execute_task,
    wrap_kickoff,
    wrap_tool_run,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler


def _handler(tracer_provider, meter_provider, logger_provider):
    return TelemetryHandler(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
    )


def _fake_crew(name="my-crew"):
    return types.SimpleNamespace(name=name)


def _fake_agent(role="researcher", model="gpt-4o"):
    return types.SimpleNamespace(
        role=role,
        llm=types.SimpleNamespace(model=model),
    )


def _fake_tool(name="search"):
    return types.SimpleNamespace(name=name)


class _Boom(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Workflow (Crew.kickoff)
# --------------------------------------------------------------------------- #


def test_kickoff_success_emits_workflow_span(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_kickoff(handler)

    def wrapped(*args, **kwargs):
        return "crew-result"

    result = traced(wrapped, _fake_crew(), (), {})

    assert result == "crew-result"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_workflow my-crew"
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "invoke_workflow"
    assert span.status.status_code == StatusCode.UNSET


def test_kickoff_falls_back_to_default_name(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_kickoff(handler)
    # Crew instance without a name attribute.
    result = traced(lambda *a, **k: "ok", types.SimpleNamespace(), (), {})

    assert result == "ok"
    (span,) = span_exporter.get_finished_spans()
    assert span.name == "invoke_workflow crew"


def test_kickoff_error_records_and_reraises(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_kickoff(handler)

    def wrapped(*args, **kwargs):
        raise _Boom("kickoff exploded")

    with pytest.raises(_Boom, match="kickoff exploded"):
        traced(wrapped, _fake_crew(), (), {})

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "invoke_workflow"
    assert (
        span.attributes[error_attributes.ERROR_TYPE] == "_Boom"
    )
    assert span.status.status_code == StatusCode.ERROR


# --------------------------------------------------------------------------- #
# Agent (Agent.execute_task)
# --------------------------------------------------------------------------- #


def test_agent_execute_task_success_emits_agent_span(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_agent_execute_task(handler)

    result = traced(lambda *a, **k: "answer", _fake_agent(), (), {})

    assert result == "answer"
    (span,) = span_exporter.get_finished_spans()
    assert span.name == "invoke_agent researcher"

    op_name = span.attributes[GenAI.GEN_AI_OPERATION_NAME]
    assert op_name == "invoke_agent"
    assert isinstance(op_name, str)

    agent_name = span.attributes[GenAI.GEN_AI_AGENT_NAME]
    assert agent_name == "researcher"
    assert isinstance(agent_name, str)

    provider = span.attributes[GenAI.GEN_AI_PROVIDER_NAME]
    assert provider == "crewai"
    assert isinstance(provider, str)

    request_model = span.attributes[GenAI.GEN_AI_REQUEST_MODEL]
    assert request_model == "gpt-4o"
    assert isinstance(request_model, str)

    assert span.status.status_code == StatusCode.UNSET


def test_agent_execute_task_without_llm_model(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_agent_execute_task(handler)
    # Agent with a role but no resolvable llm.model.
    agent = types.SimpleNamespace(role="writer", llm=None)

    traced(lambda *a, **k: "done", agent, (), {})

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "writer"
    assert GenAI.GEN_AI_REQUEST_MODEL not in span.attributes


def test_agent_execute_task_error_records_and_reraises(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_agent_execute_task(handler)

    def wrapped(*args, **kwargs):
        raise _Boom("agent exploded")

    with pytest.raises(_Boom, match="agent exploded"):
        traced(wrapped, _fake_agent(), (), {})

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "invoke_agent"
    assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "researcher"
    assert (
        span.attributes[error_attributes.ERROR_TYPE] == "_Boom"
    )
    assert span.status.status_code == StatusCode.ERROR


# --------------------------------------------------------------------------- #
# Tool (BaseTool.run)
# --------------------------------------------------------------------------- #


def test_tool_run_success_emits_tool_span(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_tool_run(handler)

    result = traced(lambda *a, **k: "tool-result", _fake_tool(), (), {})

    assert result == "tool-result"
    (span,) = span_exporter.get_finished_spans()
    assert span.name == "execute_tool search"
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"

    tool_name = span.attributes[GenAI.GEN_AI_TOOL_NAME]
    assert tool_name == "search"
    assert isinstance(tool_name, str)
    assert span.status.status_code == StatusCode.UNSET


def test_tool_run_error_records_and_reraises(
    span_exporter, tracer_provider, meter_provider, logger_provider
):
    handler = _handler(tracer_provider, meter_provider, logger_provider)
    traced = wrap_tool_run(handler)

    def wrapped(*args, **kwargs):
        raise _Boom("tool exploded")

    with pytest.raises(_Boom, match="tool exploded"):
        traced(wrapped, _fake_tool(), (), {})

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"
    assert (
        span.attributes[error_attributes.ERROR_TYPE] == "_Boom"
    )
    assert span.status.status_code == StatusCode.ERROR


# --------------------------------------------------------------------------- #
# Instrument / uninstrument wiring
# --------------------------------------------------------------------------- #


def test_instrument_wraps_and_uninstrument_unwraps(instrument):
    import crewai
    from crewai.tools.base_tool import BaseTool

    assert hasattr(crewai.crew.Crew.kickoff, "__wrapped__")
    assert hasattr(crewai.crew.Crew.kickoff_async, "__wrapped__")
    assert hasattr(crewai.agent.Agent.execute_task, "__wrapped__")
    assert hasattr(BaseTool.run, "__wrapped__")

    instrument.uninstrument()

    assert not hasattr(crewai.crew.Crew.kickoff, "__wrapped__")
    assert not hasattr(crewai.crew.Crew.kickoff_async, "__wrapped__")
    assert not hasattr(crewai.agent.Agent.execute_task, "__wrapped__")
    assert not hasattr(BaseTool.run, "__wrapped__")

    # Re-instrument so the fixture teardown's uninstrument() is balanced.
    instrument.instrument()
