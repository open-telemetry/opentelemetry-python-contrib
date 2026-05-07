# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.anthropic.wrappers import (
    AsyncMessagesStreamManagerWrapper,
    AsyncMessagesStreamWrapper,
    MessagesStreamManagerWrapper,
    MessagesStreamWrapper,
)


def _noop_stop_llm(invocation):
    del invocation


def _noop_fail_llm(invocation, error):
    del invocation
    del error


def _make_handler():
    return SimpleNamespace(
        stop_llm=_noop_stop_llm,
        fail_llm=_noop_fail_llm,
    )


def _make_invocation():
    return SimpleNamespace(attributes={}, request_model=None)


def _make_stream_wrapper(stream, handler=None):
    return MessagesStreamWrapper(
        stream=stream,
        handler=handler or _make_handler(),
        invocation=_make_invocation(),
        capture_content=False,
    )


def _make_async_stream_wrapper(stream, handler=None):
    return AsyncMessagesStreamWrapper(
        stream=stream,
        handler=handler or _make_handler(),
        invocation=_make_invocation(),
        capture_content=False,
    )


class _FakeSyncStream:
    def __init__(self, *, events=None, error=None):
        self._events = list(events or [])
        self._error = error
        self.close_calls = 0
        self.response = _FakeSyncResponse()

    def __iter__(self):
        return self

    def __next__(self):
        if self._events:
            return self._events.pop(0)
        if self._error is not None:
            raise self._error
        raise StopIteration

    def close(self):
        self.close_calls += 1


class _FakeAsyncStream:
    def __init__(self, *, events=None, error=None):
        self._events = list(events or [])
        self._error = error
        self.close_calls = 0
        self.final_message = SimpleNamespace(id="msg_final")
        self.response = _FakeAsyncResponse()

    async def __anext__(self):
        if self._events:
            return self._events.pop(0)
        if self._error is not None:
            raise self._error
        raise StopAsyncIteration

    async def close(self):
        self.close_calls += 1

    async def get_final_message(self):
        return self.final_message


class _FakeSyncManager:
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


class _FakeSyncResponse:
    def __init__(self):
        self.request_id = "req_sync"
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _FakeAsyncResponse:
    def __init__(self):
        self.request_id = "req_async"
        self.close_calls = 0
        self.aclose_calls = 0

    def close(self):
        self.close_calls += 1

    async def aclose(self):
        self.aclose_calls += 1


def test_sync_stream_wrapper_exit_closes_without_exception():
    stream = _FakeSyncStream()
    wrapper = _make_stream_wrapper(stream)
    stopped = []

    wrapper._stop = lambda: stopped.append(True)

    result = wrapper.__exit__(None, None, None)

    assert result is False
    assert stream.close_calls == 1
    assert stopped == [True]


def test_sync_stream_wrapper_exit_fails_and_closes_on_exception():
    stream = _FakeSyncStream()
    wrapper = _make_stream_wrapper(stream)
    stopped = []
    failures = []

    wrapper._stop = lambda: stopped.append(True)
    wrapper._fail = lambda message, error_type: failures.append(
        (message, error_type)
    )

    error = ValueError("boom")
    result = wrapper.__exit__(ValueError, error, None)

    assert result is False
    assert stream.close_calls == 1
    assert stopped == [True]
    assert failures == [("boom", ValueError)]


def test_sync_stream_wrapper_processes_events_and_stops_on_completion():
    event = SimpleNamespace(type="message_start")
    stream = _FakeSyncStream(events=[event])
    wrapper = _make_stream_wrapper(stream)
    processed = []
    stopped = []

    wrapper._process_chunk = processed.append
    wrapper._stop = lambda: stopped.append(True)

    result = next(wrapper)

    assert result is event
    assert processed == [event]

    with pytest.raises(StopIteration):
        next(wrapper)

    assert stopped == [True]


def test_sync_stream_wrapper_fails_and_reraises_stream_errors():
    error = ValueError("boom")
    stream = _FakeSyncStream(error=error)
    wrapper = _make_stream_wrapper(stream)
    failures = []

    wrapper._fail = lambda message, error_type: failures.append(
        (message, error_type)
    )

    with pytest.raises(ValueError, match="boom"):
        next(wrapper)

    assert failures == [("boom", ValueError)]


def test_sync_stream_wrapper_getattr_passthrough():
    stream = _FakeSyncStream()
    wrapper = _make_stream_wrapper(stream)

    assert wrapper.response.request_id == "req_sync"


def test_sync_stream_response_close_finalizes_wrapper():
    stream = _FakeSyncStream()
    wrapper = _make_stream_wrapper(stream)
    stopped = []

    wrapper._stop = lambda: stopped.append(True)

    wrapper.response.close()

    assert stream.response.close_calls == 1
    assert stopped == [True]


def test_sync_manager_enter_constructs_stream_wrapper():
    stream = _FakeSyncStream()
    wrapper = MessagesStreamManagerWrapper(
        manager=_FakeSyncManager(stream=stream),
        handler=_make_handler(),
        invocation=_make_invocation(),
        capture_content=False,
    )

    with wrapper as result:
        assert isinstance(result, MessagesStreamWrapper)
        assert result.stream is stream
        assert wrapper._stream_wrapper is result


def test_sync_manager_exit_forwards_exception_to_stream_wrapper():
    wrapper = MessagesStreamManagerWrapper(
        manager=_FakeSyncManager(stream=SimpleNamespace(), suppressed=False),
        handler=SimpleNamespace(),
        invocation=_make_invocation(),
        capture_content=False,
    )
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("boom")
    result = wrapper.__exit__(ValueError, error, None)

    assert result is False
    assert wrapper._manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)


def test_sync_manager_exit_uses_none_exception_when_manager_suppresses():
    wrapper = MessagesStreamManagerWrapper(
        manager=_FakeSyncManager(stream=SimpleNamespace(), suppressed=True),
        handler=SimpleNamespace(),
        invocation=_make_invocation(),
        capture_content=False,
    )
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = RuntimeError("ignored")
    result = wrapper.__exit__(RuntimeError, error, None)

    assert result is True
    assert wrapper._manager.exit_args == (RuntimeError, error, None)
    assert stream_wrapper.exit_args == (None, None, None)


def test_sync_manager_exit_still_finalizes_stream_wrapper_when_manager_raises():
    manager_error = RuntimeError("manager failure")
    wrapper = MessagesStreamManagerWrapper(
        manager=_FakeSyncManager(
            stream=SimpleNamespace(),
            suppressed=False,
            exit_error=manager_error,
        ),
        handler=SimpleNamespace(),
        invocation=_make_invocation(),
        capture_content=False,
    )
    stream_wrapper = _FakeStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("outer")
    with pytest.raises(RuntimeError, match="manager failure"):
        wrapper.__exit__(ValueError, error, None)

    assert wrapper._manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)


@pytest.mark.asyncio
async def test_async_stream_wrapper_exit_closes_without_exception():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []

    wrapper._stop = lambda: stopped.append(True)

    result = await wrapper.__aexit__(None, None, None)

    assert result is False
    assert stream.close_calls == 1
    assert stopped == [True]


@pytest.mark.asyncio
async def test_async_stream_wrapper_exit_fails_and_closes_on_exception():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []
    failures = []

    wrapper._stop = lambda: stopped.append(True)
    wrapper._fail = lambda message, error_type: failures.append(
        (message, error_type)
    )

    error = ValueError("boom")
    result = await wrapper.__aexit__(ValueError, error, None)

    assert result is False
    assert stream.close_calls == 1
    assert stopped == [True]
    assert failures == [("boom", ValueError)]


@pytest.mark.asyncio
async def test_async_stream_wrapper_close_uses_close_and_stops():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []

    wrapper._stop = lambda: stopped.append(True)

    await wrapper.close()

    assert stream.close_calls == 1
    assert stopped == [True]


@pytest.mark.asyncio
async def test_async_stream_wrapper_processes_events_and_stops_on_completion():
    event = SimpleNamespace(type="message_start")
    stream = _FakeAsyncStream(events=[event])
    wrapper = _make_async_stream_wrapper(stream)
    processed = []
    stopped = []

    wrapper._process_chunk = processed.append
    wrapper._stop = lambda: stopped.append(True)

    result = await anext(wrapper)

    assert result is event
    assert processed == [event]

    with pytest.raises(StopAsyncIteration):
        await anext(wrapper)

    assert stopped == [True]


@pytest.mark.asyncio
async def test_async_stream_wrapper_fails_and_reraises_stream_errors():
    error = ValueError("boom")
    stream = _FakeAsyncStream(error=error)
    wrapper = _make_async_stream_wrapper(stream)
    failures = []

    wrapper._fail = lambda message, error_type: failures.append(
        (message, error_type)
    )

    with pytest.raises(ValueError, match="boom"):
        await anext(wrapper)

    assert failures == [("boom", ValueError)]


@pytest.mark.asyncio
async def test_async_stream_wrapper_preserves_stream_helper_methods():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)

    result = await wrapper.get_final_message()

    assert result is stream.final_message
    assert wrapper.response.request_id == "req_async"


@pytest.mark.asyncio
async def test_async_stream_response_aclose_finalizes_wrapper():
    stream = _FakeAsyncStream()
    wrapper = _make_async_stream_wrapper(stream)
    stopped = []

    wrapper._stop = lambda: stopped.append(True)

    await wrapper.response.aclose()

    assert stream.response.aclose_calls == 1
    assert stopped == [True]


@pytest.mark.asyncio
async def test_async_manager_enter_constructs_async_stream_wrapper():
    stream = _FakeAsyncStream()
    wrapper = AsyncMessagesStreamManagerWrapper(
        manager=_FakeAsyncManager(stream=stream),
        handler=_make_handler(),
        invocation=_make_invocation(),
        capture_content=False,
    )

    async with wrapper as result:
        assert isinstance(result, AsyncMessagesStreamWrapper)
        assert result.stream is stream
        assert wrapper._stream_wrapper is result


@pytest.mark.asyncio
async def test_async_manager_exit_forwards_exception_to_stream_wrapper():
    wrapper = AsyncMessagesStreamManagerWrapper(
        manager=_FakeAsyncManager(stream=SimpleNamespace(), suppressed=False),
        handler=SimpleNamespace(),
        invocation=_make_invocation(),
        capture_content=False,
    )
    stream_wrapper = _FakeAsyncStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("boom")
    result = await wrapper.__aexit__(ValueError, error, None)

    assert result is False
    assert wrapper._manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)


@pytest.mark.asyncio
async def test_async_manager_exit_uses_none_exception_when_manager_suppresses():
    wrapper = AsyncMessagesStreamManagerWrapper(
        manager=_FakeAsyncManager(stream=SimpleNamespace(), suppressed=True),
        handler=SimpleNamespace(),
        invocation=_make_invocation(),
        capture_content=False,
    )
    stream_wrapper = _FakeAsyncStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = RuntimeError("ignored")
    result = await wrapper.__aexit__(RuntimeError, error, None)

    assert result is True
    assert wrapper._manager.exit_args == (RuntimeError, error, None)
    assert stream_wrapper.exit_args == (None, None, None)


@pytest.mark.asyncio
async def test_async_manager_exit_still_finalizes_stream_wrapper_when_manager_raises():
    manager_error = RuntimeError("manager failure")
    wrapper = AsyncMessagesStreamManagerWrapper(
        manager=_FakeAsyncManager(
            stream=SimpleNamespace(),
            suppressed=False,
            exit_error=manager_error,
        ),
        handler=SimpleNamespace(),
        invocation=_make_invocation(),
        capture_content=False,
    )
    stream_wrapper = _FakeAsyncStreamWrapper()
    wrapper._stream_wrapper = stream_wrapper

    error = ValueError("outer")
    with pytest.raises(RuntimeError, match="manager failure"):
        await wrapper.__aexit__(ValueError, error, None)

    assert wrapper._manager.exit_args == (ValueError, error, None)
    assert stream_wrapper.exit_args == (ValueError, error, None)
