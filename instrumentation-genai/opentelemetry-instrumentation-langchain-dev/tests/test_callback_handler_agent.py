# Copyright The OpenTelemetry Authors
from __future__ import annotations

from typing import Optional, Tuple
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from opentelemetry.sdk.trace import TracerProvider

from opentelemetry.instrumentation.langchain.callback_handler import (
    TraceloopCallbackHandler,
)


class _StubTelemetryHandler:
    def __init__(self) -> None:
        self.started_agents = []
        self.stopped_agents = []
        self.failed_agents = []
        self.started_llms = []
        self.stopped_llms = []

    def start_agent(self, agent):
        self.started_agents.append(agent)
        return agent

    def stop_agent(self, agent):
        self.stopped_agents.append(agent)
        return agent

    def fail_agent(self, agent, error):
        self.failed_agents.append((agent, error))
        return agent

    def start_llm(self, invocation):
        self.started_llms.append(invocation)
        return invocation

    def stop_llm(self, invocation):
        self.stopped_llms.append(invocation)
        return invocation

    def evaluate_llm(self, invocation):  # pragma: no cover - simple stub
        return []


@pytest.fixture()
def handler_with_stub() -> Tuple[TraceloopCallbackHandler, _StubTelemetryHandler]:
    tracer = TracerProvider().get_tracer(__name__)
    histogram = MagicMock()
    histogram.record = MagicMock()
    handler = TraceloopCallbackHandler(tracer, histogram, histogram)
    stub = _StubTelemetryHandler()
    handler._telemetry_handler = stub  # type: ignore[attr-defined]
    return handler, stub


def test_agent_invocation_links_util_handler(handler_with_stub):
    handler, stub = handler_with_stub

    agent_run_id = uuid4()
    handler.on_chain_start(
        serialized={"name": "AgentExecutor", "id": ["langchain", "agents", "AgentExecutor"]},
        inputs={"input": "plan my trip"},
        run_id=agent_run_id,
        tags=["agent"],
        metadata={"ls_agent_type": "react", "ls_model_name": "gpt-4"},
    )

    assert stub.started_agents, "Agent start was not forwarded to util handler"
    agent = stub.started_agents[-1]
    assert agent.operation == "invoke"
    assert agent.input_context and "plan my trip" in agent.input_context

    llm_run_id = uuid4()
    handler.on_chat_model_start(
        serialized={"name": "ChatOpenAI"},
        messages=[[HumanMessage(content="hello")]],
        run_id=llm_run_id,
        parent_run_id=agent_run_id,
        invocation_params={"model_name": "gpt-4"},
        metadata={"ls_provider": "openai"},
    )

    assert stub.started_llms, "LLM invocation was not recorded"
    llm_invocation = stub.started_llms[-1]
    assert llm_invocation.run_id == llm_run_id
    assert llm_invocation.parent_run_id == agent_run_id
    assert llm_invocation.agent_name == agent.name
    assert llm_invocation.agent_id == str(agent.run_id)

    handler.on_chain_end(outputs={"result": "done"}, run_id=agent_run_id)

    assert stub.stopped_agents, "Agent stop was not forwarded to util handler"
    stopped_agent = stub.stopped_agents[-1]
    assert stopped_agent.output_result and "done" in stopped_agent.output_result
    assert agent_run_id not in handler._agents  # type: ignore[attr-defined]


def test_agent_failure_forwards_to_util(handler_with_stub):
    handler, stub = handler_with_stub

    failing_run_id = uuid4()
    handler.on_chain_start(
        serialized={"name": "AgentExecutor"},
        inputs={},
        run_id=failing_run_id,
    )

    error = RuntimeError("boom")
    handler.on_chain_error(error, run_id=failing_run_id)

    assert stub.failed_agents, "Agent failure was not propagated"
    failed_agent, recorded_error = stub.failed_agents[-1]
    assert failed_agent.run_id == failing_run_id
    assert recorded_error.message == str(error)
    assert recorded_error.type is RuntimeError
    assert failing_run_id not in handler._agents  # type: ignore[attr-defined]


def test_llm_attributes_independent_of_emitters(monkeypatch):
    def _build_handler() -> Tuple[TraceloopCallbackHandler, _StubTelemetryHandler]:
        tracer = TracerProvider().get_tracer(__name__)
        histogram = MagicMock()
        histogram.record = MagicMock()
        handler = TraceloopCallbackHandler(tracer, histogram, histogram)
        stub_handler = _StubTelemetryHandler()
        handler._telemetry_handler = stub_handler  # type: ignore[attr-defined]
        return handler, stub_handler

    def _invoke_with_env(env_value: Optional[str]):
        if env_value is None:
            monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_EMITTERS", raising=False)
        else:
            monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_EMITTERS", env_value)

        handler, stub_handler = _build_handler()
        run_id = uuid4()
        handler.on_chat_model_start(
            serialized={"name": "ChatOpenAI", "id": ["langchain", "ChatOpenAI"]},
            messages=[[HumanMessage(content="hi")]],
            run_id=run_id,
            invocation_params={
                "model_name": "gpt-4",
                "top_p": 0.5,
                "seed": 42,
                "model_kwargs": {"user": "abc"},
            },
            metadata={
                "ls_provider": "openai",
                "ls_max_tokens": 256,
                "custom_meta": "value",
            },
            tags=["agent"],
        )
        return stub_handler.started_llms[-1]

    invocation_default = _invoke_with_env(None)
    invocation_traceloop = _invoke_with_env("traceloop_compat")

    assert (
        invocation_default.attributes == invocation_traceloop.attributes
    ), "Emitter env toggle should not change recorded attributes"

    attrs = invocation_default.attributes
    assert invocation_default.request_model == "gpt-4"
    assert invocation_default.provider == "openai"
    assert attrs["request_top_p"] == 0.5
    assert attrs["request_seed"] == 42
    assert attrs["request_max_tokens"] == 256
    assert attrs["custom_meta"] == "value"
    assert attrs["tags"] == ["agent"]
    assert attrs["callback.name"] == "ChatOpenAI"
    assert attrs["traceloop.callback_name"] == "ChatOpenAI"
    assert attrs["callback.id"] == ["langchain", "ChatOpenAI"]
    assert "ls_provider" not in attrs
    assert "ls_max_tokens" not in attrs
    assert "ls_model_name" not in attrs
    assert "model_kwargs" in attrs
