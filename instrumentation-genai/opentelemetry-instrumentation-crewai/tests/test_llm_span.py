# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.crewai._wrappers import (
    _pending_llm_calls,
    on_llm_call_completed,
    wrap_llm_call,
)
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import StatusCode

from .conftest import fake_llm


def _fake_completed_event(**overrides):
    defaults = dict(
        usage={
            "prompt_tokens": 12,
            "completion_tokens": 34,
            "total_tokens": 46,
        },
        finish_reason="stop",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_llm_span_has_genai_attributes(handler_and_exporter):
    handler, exporter = handler_and_exporter
    llm = fake_llm(model="gpt-4o-mini", provider="openai")
    wrapper = wrap_llm_call(handler)

    def wrapped(*args, **kwargs):
        # Simulates crewai_event_bus dispatching LLMCallCompletedEvent
        # before call() returns, just as the real BaseLLM subclasses do.
        on_llm_call_completed(llm, _fake_completed_event())
        return "the answer"

    result = wrapper(wrapped, llm, ("hello",), {})

    assert result == "the answer"
    (span,) = exporter.get_finished_spans()
    assert span.name == "chat gpt-4o-mini"
    assert (
        span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
        == "gpt-4o-mini"
    )
    assert span.attributes[gen_ai_attributes.GEN_AI_PROVIDER_NAME] == "openai"
    assert span.attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert span.attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 34
    assert span.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS
    ] == ("stop",)


def test_llm_span_omits_content_by_default(handler_and_exporter):
    handler, exporter = handler_and_exporter
    llm = fake_llm()
    wrapper = wrap_llm_call(handler)

    def wrapped(*args, **kwargs):
        on_llm_call_completed(llm, _fake_completed_event())
        return "secret answer"

    wrapper(wrapped, llm, ("secret prompt",), {})

    (span,) = exporter.get_finished_spans()
    assert gen_ai_attributes.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes


def test_llm_span_captures_content_when_flag_enabled(
    content_capturing_handler_and_exporter,
):
    handler, exporter = content_capturing_handler_and_exporter
    llm = fake_llm()
    wrapper = wrap_llm_call(handler)

    def wrapped(*args, **kwargs):
        on_llm_call_completed(llm, _fake_completed_event())
        return "the real answer"

    wrapper(wrapped, llm, ("the real prompt",), {})

    (span,) = exporter.get_finished_spans()
    assert (
        "the real prompt"
        in span.attributes[gen_ai_attributes.GEN_AI_INPUT_MESSAGES]
    )
    assert (
        "the real answer"
        in span.attributes[gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES]
    )


def test_llm_span_records_exception_and_reraises(handler_and_exporter):
    handler, exporter = handler_and_exporter
    llm = fake_llm()
    wrapper = wrap_llm_call(handler)

    def wrapped(*args, **kwargs):
        raise TimeoutError("provider timed out")

    with pytest.raises(TimeoutError, match="provider timed out"):
        wrapper(wrapped, llm, ("hi",), {})

    (span,) = exporter.get_finished_spans()
    assert span.name == "chat gpt-4o-mini"
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[error_attributes.ERROR_TYPE] == "TimeoutError"


def test_concurrent_calls_on_different_instances_do_not_cross_talk(
    handler_and_exporter,
):
    """The common concurrent case: two agents, each with their own LLM
    instance, calling the model at the same time. id(instance) differs, so
    each call must land its own usage data on its own span -- never the
    other's."""
    handler, exporter = handler_and_exporter
    llm_a = fake_llm(model="model-a")
    llm_b = fake_llm(model="model-b")
    wrapper = wrap_llm_call(handler)
    barrier = threading.Barrier(2)

    def run(llm, tag, delay):
        def wrapped(*args, **kwargs):
            barrier.wait(timeout=5)  # force real overlap between the two calls
            time.sleep(delay)
            on_llm_call_completed(
                llm,
                _fake_completed_event(
                    usage={"prompt_tokens": tag, "completion_tokens": tag}
                ),
            )
            return f"answer-{tag}"

        wrapper(wrapped, llm, (f"prompt-{tag}",), {})

    thread_a = threading.Thread(target=run, args=(llm_a, 1, 0.05))
    thread_b = threading.Thread(target=run, args=(llm_b, 2, 0.0))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    spans = {
        s.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]: s
        for s in exporter.get_finished_spans()
    }
    assert (
        spans["model-a"].attributes[
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
        ]
        == 1
    )
    assert (
        spans["model-b"].attributes[
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
        ]
        == 2
    )
    assert (
        not _pending_llm_calls
    )  # no leaked queue entries after both complete


def test_back_to_back_calls_on_shared_instance_do_not_leak_state(
    handler_and_exporter,
):
    """A single LLM instance reused for two sequential (non-overlapping)
    calls -- the realistic "shared LLM object" case when calls don't
    actually overlap. The second call must not see the first call's event."""
    handler, exporter = handler_and_exporter
    llm = fake_llm()
    wrapper = wrap_llm_call(handler)

    def wrapped_one(*args, **kwargs):
        on_llm_call_completed(llm, _fake_completed_event(finish_reason="stop"))
        return "first"

    def wrapped_two(*args, **kwargs):
        on_llm_call_completed(
            llm, _fake_completed_event(finish_reason="length")
        )
        return "second"

    wrapper(wrapped_one, llm, ("p1",), {})
    wrapper(wrapped_two, llm, ("p2",), {})

    span_one, span_two = exporter.get_finished_spans()
    assert span_one.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS
    ] == ("stop",)
    assert span_two.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS
    ] == ("length",)
    assert not _pending_llm_calls
