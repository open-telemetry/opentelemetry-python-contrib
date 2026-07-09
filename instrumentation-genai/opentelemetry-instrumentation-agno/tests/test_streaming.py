# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Streaming behavior of the agno ``run``/``arun`` wrappers.

``Agent.run(stream=True)`` returns an iterator and ``Agent.arun(stream=True)``
returns an async generator (not an awaitable). The wrappers must preserve those
calling conventions and keep the span open until the stream is consumed.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.agno.patch import agent_arun, agent_run

_INSTANCE = SimpleNamespace(
    model=SimpleNamespace(id="gpt-4o"), name="assistant"
)


def _single_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def test_sync_run_streaming_keeps_span_open_until_consumed(
    handler, span_exporter
):
    def wrapped(*args, **kwargs):
        yield from ("a", "b", "c")

    result = agent_run(handler)(wrapped, _INSTANCE, (), {"stream": True})

    # The span must not close before the returned iterator is consumed.
    assert not span_exporter.get_finished_spans()
    assert list(result) == ["a", "b", "c"]
    _single_span(span_exporter)


def test_async_arun_streaming_returns_async_iterator(handler, span_exporter):
    async def wrapped(*args, **kwargs):
        for item in ("a", "b"):
            yield item

    async def scenario():
        # Must be an async iterator, not a coroutine (awaiting an async
        # generator raises "object async_generator can't be used in 'await'").
        result = agent_arun(handler)(wrapped, _INSTANCE, (), {"stream": True})
        assert hasattr(result, "__aiter__")
        return [item async for item in result]

    assert asyncio.run(scenario()) == ["a", "b"]
    _single_span(span_exporter)


def test_async_arun_non_streaming_awaits_result(handler, span_exporter):
    async def wrapped(*args, **kwargs):
        return "done"

    async def scenario():
        return await agent_arun(handler)(wrapped, _INSTANCE, (), {})

    assert asyncio.run(scenario()) == "done"
    _single_span(span_exporter)


def test_sync_run_streaming_without_stream_kwarg(handler, span_exporter):
    # ``Agent(stream=True)`` enables streaming from the agent-level default, so
    # ``run()`` returns an iterator even when no ``stream`` kwarg is passed.
    # Streaming must be detected from the result, not ``kwargs["stream"]``.
    def wrapped(*args, **kwargs):
        yield from ("a", "b", "c")

    result = agent_run(handler)(wrapped, _INSTANCE, (), {})

    assert not span_exporter.get_finished_spans()
    assert list(result) == ["a", "b", "c"]
    _single_span(span_exporter)


def test_async_arun_streaming_without_stream_kwarg(handler, span_exporter):
    # ``Agent(stream=True)`` makes ``arun()`` return an async generator even
    # without a ``stream`` kwarg; the wrapper must not try to await it.
    async def wrapped(*args, **kwargs):
        for item in ("a", "b"):
            yield item

    async def scenario():
        result = agent_arun(handler)(wrapped, _INSTANCE, (), {})
        assert hasattr(result, "__aiter__")
        return [item async for item in result]

    assert asyncio.run(scenario()) == ["a", "b"]
    _single_span(span_exporter)


def test_async_arun_streaming_records_error(handler, span_exporter):
    async def wrapped(*args, **kwargs):
        if False:  # make this an async generator function
            yield None
        raise ValueError("boom")

    async def scenario():
        result = agent_arun(handler)(wrapped, _INSTANCE, (), {"stream": True})
        return [item async for item in result]

    with pytest.raises(ValueError):
        asyncio.run(scenario())
    span = _single_span(span_exporter)
    assert span.status.status_code.name == "ERROR"
