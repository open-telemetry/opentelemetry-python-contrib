# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from opentelemetry.instrumentation.crewai._wrappers import wrap_crew_kickoff
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode

from .conftest import fake_agent, fake_crew, fake_task


def test_kickoff_produces_one_span_with_expected_attributes(
    handler_and_exporter,
):
    handler, exporter = handler_and_exporter
    crew = fake_crew(
        agents=[fake_agent(), fake_agent(role="Writer")],
        tasks=[fake_task(), fake_task()],
        process="sequential",
        crew_id="crew-123",
    )
    wrapper = wrap_crew_kickoff(handler)

    def wrapped(*args, **kwargs):
        return "crew output"

    result = wrapper(wrapped, crew, (), {})

    assert result == "crew output"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    (span,) = spans
    assert span.name == "invoke_workflow crew.kickoff"
    assert span.attributes["crewai.crew.id"] == "crew-123"
    assert span.attributes["crewai.crew.process"] == "sequential"
    assert span.attributes["crewai.crew.agent_count"] == 2
    assert span.attributes["crewai.crew.task_count"] == 2


def test_kickoff_records_exception_and_reraises(handler_and_exporter):
    handler, exporter = handler_and_exporter
    crew = fake_crew()
    wrapper = wrap_crew_kickoff(handler)

    def wrapped(*args, **kwargs):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        wrapper(wrapped, crew, (), {})

    (span,) = exporter.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[error_attributes.ERROR_TYPE] == "ValueError"
