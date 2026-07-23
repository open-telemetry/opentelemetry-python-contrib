# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from crewai.utilities.constants import NOT_SPECIFIED

from opentelemetry.instrumentation.crewai import _wrappers
from opentelemetry.instrumentation.crewai._wrappers import (
    _reset_handoff_state,
    wrap_agent_execute_task,
    wrap_crew_kickoff,
)

from .conftest import fake_agent, fake_crew, fake_task


def test_second_agent_links_to_first_when_context_explicit(
    handler_and_exporter,
):
    handler, exporter = handler_and_exporter
    crew = fake_crew()
    agent_a = fake_agent(role="Researcher", crew=crew)
    agent_b = fake_agent(role="Writer", crew=crew)
    task_a = fake_task(context=None)
    task_b = fake_task(context=[task_a])

    wrapper = wrap_agent_execute_task(handler)
    _reset_handoff_state(crew)

    kickoff_invocation = handler.start_workflow(name="crew.kickoff")
    wrapper(lambda *a, **k: "research output", agent_a, (task_a,), {})
    wrapper(lambda *a, **k: "final output", agent_b, (task_b,), {})
    kickoff_invocation.stop()

    spans = {
        s.attributes.get("crewai.agent.role"): s
        for s in exporter.get_finished_spans()
    }
    span_a, span_b = spans["Researcher"], spans["Writer"]
    kickoff_span = spans[None]

    # It's a link, not a parent-child relationship: both are direct children
    # of the crew.kickoff span, not of each other.
    assert span_a.parent.span_id == kickoff_span.context.span_id
    assert span_b.parent.span_id == kickoff_span.context.span_id
    assert span_b.parent.span_id != span_a.context.span_id

    assert len(span_b.links) == 1
    assert span_b.links[0].context.span_id == span_a.context.span_id
    assert span_a.links == ()


def test_default_context_links_to_every_prior_task(handler_and_exporter):
    """Task.context left unset (NOT_SPECIFIED) means CrewAI feeds every prior
    task's output into this one -- the handoff links should match."""
    handler, exporter = handler_and_exporter
    crew = fake_crew()
    agent_a = fake_agent(role="A", crew=crew)
    agent_b = fake_agent(role="B", crew=crew)
    agent_c = fake_agent(role="C", crew=crew)
    task_a = fake_task(context=None)
    task_b = fake_task(context=None)
    task_c = fake_task(context=NOT_SPECIFIED)

    wrapper = wrap_agent_execute_task(handler)
    _reset_handoff_state(crew)

    kickoff_invocation = handler.start_workflow(name="crew.kickoff")
    wrapper(lambda *a, **k: "a", agent_a, (task_a,), {})
    wrapper(lambda *a, **k: "b", agent_b, (task_b,), {})
    wrapper(lambda *a, **k: "c", agent_c, (task_c,), {})
    kickoff_invocation.stop()

    spans = {
        s.attributes.get("crewai.agent.role"): s
        for s in exporter.get_finished_spans()
    }
    linked_ids = {link.context.span_id for link in spans["C"].links}
    assert linked_ids == {
        spans["A"].context.span_id,
        spans["B"].context.span_id,
    }


def test_no_context_means_no_links(handler_and_exporter):
    handler, exporter = handler_and_exporter
    crew = fake_crew()
    agent_a = fake_agent(role="A", crew=crew)
    agent_b = fake_agent(role="B", crew=crew)
    task_a = fake_task(context=None)
    task_b = fake_task(context=None)  # explicit "no dependency"

    wrapper = wrap_agent_execute_task(handler)
    _reset_handoff_state(crew)

    kickoff_invocation = handler.start_workflow(name="crew.kickoff")
    wrapper(lambda *a, **k: "a", agent_a, (task_a,), {})
    wrapper(lambda *a, **k: "b", agent_b, (task_b,), {})
    kickoff_invocation.stop()

    spans = {
        s.attributes.get("crewai.agent.role"): s
        for s in exporter.get_finished_spans()
    }
    assert spans["B"].links == ()


def test_handoff_state_is_scoped_per_crew_run(handler_and_exporter):
    """wrap_crew_kickoff must clear id(crew)'s entry out of the shared,
    module-level handoff dict once the run ends, so state from one run can
    never leak into a later, unrelated run against the same Crew object."""
    handler, _exporter = handler_and_exporter
    crew = fake_crew()
    kickoff_wrapper = wrap_crew_kickoff(handler)
    agent_wrapper = wrap_agent_execute_task(handler)
    agent = fake_agent(role="A", crew=crew)
    task = fake_task(context=None)

    def run_with_one_agent_task(*args, **kwargs):
        assert id(crew) in _wrappers._handoff_spans
        agent_wrapper(lambda *a, **k: "out", agent, (task,), {})
        return "crew done"

    kickoff_wrapper(run_with_one_agent_task, crew, (), {})

    assert id(crew) not in _wrappers._handoff_spans
