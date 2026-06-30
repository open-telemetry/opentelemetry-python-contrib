# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.openai_v2.response_wrappers import (
    AsyncResponseStreamManagerWrapper,
    AsyncResponseStreamWrapper,
    ResponseStreamManagerWrapper,
    ResponseStreamWrapper,
)


class _FakeManager:
    def __init__(self, stream, suppressed=False, exit_error=None):
        self._stream = stream
        self._suppressed = suppressed
        self._exit_error = exit_error
        self.exit_args = None

    def __enter__(self):
        return self._stream

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_args = (exc_type, exc_val, exc_tb)
        if self._exit_error is not None:
            raise self._exit_error
        return self._suppressed


class _FakeAsyncManager:
    def __init__(self, stream, suppressed=False, exit_error=None):
        self._stream = stream
        self._suppressed = suppressed
        self._exit_error = exit_error
        self.exit_args = None

    async def __aenter__(self):
        return self._stream

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exit_args = (exc_type, exc_val, exc_tb)
        if self._exit_error is not None:
            raise self._exit_error
        return self._suppressed


def _noop_stop():
    return None


def _noop_fail(error):
    del error


def _make_wrapper(manager):
    invocation = SimpleNamespace(
        request_model=None,
        stop=_noop_stop,
        fail=_noop_fail,
    )
    return ResponseStreamManagerWrapper(
        manager=manager,
        invocation=invocation,
        capture_content=False,
    )


def _make_stream_wrapper(stream, invocation=None):
    if invocation is None:
        invocation = SimpleNamespace(
            request_model=None,
            stop=_noop_stop,
            fail=_noop_fail,
        )
    return ResponseStreamWrapper(
        stream=stream,
        invocation=invocation,
        capture_content=False,
    )


def _make_async_manager_wrapper(manager):
    invocation = SimpleNamespace(
        request_model=None,
        stop=_noop_stop,
        fail=_noop_fail,
    )
    return AsyncResponseStreamManagerWrapper(
        manager=manager,
        invocation=invocation,
        capture_content=False,
    )


def _make_async_stream_wrapper(stream, invocation=None):
    if invocation is None:
        invocation = SimpleNamespace(
            request_model=None,
            stop=_noop_stop,
            fail=_noop_fail,
        )
    return AsyncResponseStreamWrapper(
        stream=stream,
        invocation=invocation,
        capture_content=False,
    )


class _FakeStreamWrapper:
    def __init__(self):
        self.exit_args = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_args = (exc_type, exc_val, exc_tb)
        return False


class _FakeAsyncStreamWrapper:
    def __init__(self):
        self.exit_args = None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exit_args = (exc_type, exc_val, exc_tb)
        return False


class _FakeAsyncResponse:
    def __init__(self):
        self.aclose_calls = 0

    async def aclose(self):
        self.aclose_calls += 1


class _FakeSyncResponse:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _FakeAsyncStream:
    def __init__(
        self,
        *,
        events=None,
        error=None,
        final_response=None,
        response=None,
    ):
        self._events = list(events or [])
        self._error = error
        self._final_response = final_response
        self._response = response
        self.close_calls = 0
        self.get_final_response_calls = 0

    async def __anext__(self):
        if self._events:
            return self._events.pop(0)
        if self._error is not None:
            raise self._error
        raise StopAsyncIteration

    async def close(self):
        self.close_calls += 1

    async def get_final_response(self):
        self.get_final_response_calls += 1
        return self._final_response


def test_manager_exit_forwards_exception_to_stream_wrapper():
    manager = _FakeManager(stream=SimpleNamespace(), suppressed=False)
    wrapper = _make_wrapper(manager)
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("boom")
    result = wrapper.__exit__(ValueError, error, None)

    assert result is False
    assert manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
    assert wrapper._stream_wrapper is None


def test_manager_exit_uses_none_exception_when_manager_suppresses():
    manager = _FakeManager(stream=SimpleNamespace(), suppressed=True)
    wrapper = _make_wrapper(manager)
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = RuntimeError("ignored")
    result = wrapper.__exit__(RuntimeError, error, None)

    assert result is True
    assert manager.exit_args == (RuntimeError, error, None)
    assert stream_wrapper.exit_args == (None, None, None)
    assert wrapper._stream_wrapper is None


def test_manager_exit_still_finalizes_stream_wrapper_when_manager_raises():
    manager_error = RuntimeError("manager failure")
    manager = _FakeManager(
        stream=SimpleNamespace(), suppressed=False, exit_error=manager_error
    )
    wrapper = _make_wrapper(manager)
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("outer")
    with pytest.raises(RuntimeError, match="manager failure"):
        wrapper.__exit__(ValueError, error, None)

    assert manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
    assert wrapper._stream_wrapper is None


def test_stream_wrapper_response_falls_back_to_public_response_attr():
    response = _FakeSyncResponse()
    stream = SimpleNamespace(response=response)
    wrapper = _make_stream_wrapper(stream)
    stopped = []

    wrapper._stop = stopped.append

    wrapper.response.close()

    assert response.close_calls == 1
    assert stopped == [None]


@pytest.mark.asyncio
async def test_async_manager_exit_forwards_exception_to_stream_wrapper():
    manager = _FakeAsyncManager(stream=SimpleNamespace(), suppressed=False)
    wrapper = _make_async_manager_wrapper(manager)
    stream_wrapper = _FakeAsyncStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("boom")
    result = await wrapper.__aexit__(ValueError, error, None)

    assert result is False
    assert manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
    assert wrapper._stream_wrapper is None


@pytest.mark.asyncio
async def test_async_manager_enter_constructs_async_stream_wrapper():
    stream = _FakeAsyncStream()
    manager = _FakeAsyncManager(stream=stream)
    wrapper = _make_async_manager_wrapper(manager)

    async with wrapper as result:
        assert isinstance(result, AsyncResponseStreamWrapper)
        assert result.stream is stream
        assert wrapper._stream_wrapper is result


@pytest.mark.asyncio
async def test_async_manager_exit_uses_none_exception_when_manager_suppresses():
    manager = _FakeAsyncManager(stream=SimpleNamespace(), suppressed=True)
    wrapper = _make_async_manager_wrapper(manager)
    stream_wrapper = _FakeAsyncStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = RuntimeError("ignored")
    result = await wrapper.__aexit__(RuntimeError, error, None)

    assert result is True
    assert manager.exit_args == (RuntimeError, error, None)
    assert stream_wrapper.exit_args == (None, None, None)
    assert wrapper._stream_wrapper is None


@pytest.mark.asyncio
async def test_async_manager_exit_still_finalizes_stream_wrapper_when_manager_raises():
    manager_error = RuntimeError("manager failure")
    manager = _FakeAsyncManager(
        stream=SimpleNamespace(), suppressed=False, exit_error=manager_error
    )
    wrapper = _make_async_manager_wrapper(manager)
    stream_wrapper = _FakeAsyncStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("outer")
    with pytest.raises(RuntimeError, match="manager failure"):
        await wrapper.__aexit__(ValueError, error, None)

    assert manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
    assert wrapper._stream_wrapper is None


@pytest.mark.asyncio
async def test_async_stream_wrapper_exit_closes_without_exception():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []

    wrapper._stop = stopped.append

    result = await wrapper.__aexit__(None, None, None)

    assert result is False
    assert stream.close_calls == 1
    assert stopped == [None]


@pytest.mark.asyncio
async def test_async_stream_wrapper_exit_fails_and_closes_on_exception():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []
    failures = []

    def record_failure(message, error_type):
        failures.append((message, error_type))

    wrapper._stop = stopped.append
    wrapper._fail = record_failure

    error = ValueError("boom")
    result = await wrapper.__aexit__(ValueError, error, None)

    assert result is False
    assert stream.close_calls == 1
    assert stopped == [None]
    assert failures == [("boom", ValueError)]


@pytest.mark.asyncio
async def test_async_stream_wrapper_close_closes_stream_and_stops():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []

    wrapper._stop = stopped.append

    await wrapper.close()

    assert stream.close_calls == 1
    assert stopped == [None]


@pytest.mark.asyncio
async def test_async_stream_wrapper_processes_events_and_stops_on_completion():
    event = SimpleNamespace(type="response.created")
    stream = _FakeAsyncStream(events=[event])
    wrapper = _make_async_stream_wrapper(stream)
    processed = []
    stopped = []

    wrapper.process_event = processed.append
    wrapper._stop = stopped.append

    result = await anext(wrapper)

    assert result is event
    assert processed == [event]

    with pytest.raises(StopAsyncIteration):
        await anext(wrapper)

    assert stopped == [None]


@pytest.mark.asyncio
async def test_async_stream_wrapper_until_done_consumes_stream():
    events = [
        SimpleNamespace(type="response.created"),
        SimpleNamespace(type="response.in_progress"),
    ]
    stream = _FakeAsyncStream(events=events)
    wrapper = _make_async_stream_wrapper(stream)
    processed = []
    stopped = []

    wrapper.process_event = processed.append
    wrapper._stop = stopped.append

    result = await wrapper.until_done()

    assert result is wrapper
    assert processed == events
    assert stopped == [None]


@pytest.mark.asyncio
async def test_async_stream_wrapper_fails_and_reraises_stream_errors():
    error = ValueError("boom")
    stream = _FakeAsyncStream(error=error)
    wrapper = _make_async_stream_wrapper(stream)
    failures = []

    def record_failure(message, error_type):
        failures.append((message, error_type))

    wrapper._fail = record_failure

    with pytest.raises(ValueError, match="boom"):
        await anext(wrapper)

    assert failures == [("boom", ValueError)]


@pytest.mark.asyncio
async def test_async_stream_response_aclose_finalizes_wrapper():
    response = _FakeAsyncResponse()
    stream = _FakeAsyncStream(response=response)
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []

    wrapper._stop = stopped.append

    await wrapper.response.aclose()

    assert response.aclose_calls == 1
    assert stopped == [None]


@pytest.mark.asyncio
async def test_async_stream_response_is_none_when_stream_has_no_response():
    wrapper = _make_async_stream_wrapper(SimpleNamespace())

    assert wrapper.response is None


@pytest.mark.asyncio
async def test_async_stream_get_final_response_waits_for_completion():
    event = SimpleNamespace(type="response.in_progress")
    final_response = SimpleNamespace(id="response_123")
    stream = _FakeAsyncStream(events=[event], final_response=final_response)
    wrapper = _make_async_stream_wrapper(stream)

    wrapper.process_event = lambda current: current

    result = await wrapper.get_final_response()

    assert result is final_response
    assert stream.get_final_response_calls == 1
