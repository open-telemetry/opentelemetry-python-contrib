# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from opentelemetry.instrumentation.crewai._wrappers import (
    wrap_agent_execute_task,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode

from .conftest import fake_agent, fake_task


def test_agent_span_nests_under_active_kickoff_span(handler_and_exporter):
    handler, exporter = handler_and_exporter
    wrapper = wrap_agent_execute_task(handler)
    agent = fake_agent()
    task = fake_task()

    kickoff_invocation = handler.start_workflow(name="crew.kickoff")
    wrapper(lambda *a, **k: "agent output", agent, (task,), {})
    kickoff_invocation.stop()

    spans = exporter.get_finished_spans()
    names = {s.name: s for s in spans}
    assert set(names) == {
        "invoke_workflow crew.kickoff",
        "invoke_agent Researcher",
    }
    agent_span = names["invoke_agent Researcher"]
    kickoff_span = names["invoke_workflow crew.kickoff"]
    assert agent_span.parent.span_id == kickoff_span.context.span_id
    assert agent_span.attributes["crewai.agent.role"] == "Researcher"


def test_agent_span_records_exception_and_reraises(handler_and_exporter):
    handler, exporter = handler_and_exporter
    wrapper = wrap_agent_execute_task(handler)
    agent = fake_agent()
    task = fake_task()

    def wrapped(*args, **kwargs):
        raise RuntimeError("agent failed")

    with pytest.raises(RuntimeError, match="agent failed"):
        wrapper(wrapped, agent, (task,), {})

    (span,) = exporter.get_finished_spans()
    assert span.name == "invoke_agent Researcher"
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[error_attributes.ERROR_TYPE] == "RuntimeError"
