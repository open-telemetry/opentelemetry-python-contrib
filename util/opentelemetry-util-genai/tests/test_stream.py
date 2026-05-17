# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=abstract-class-instantiated

import asyncio
import inspect

import pytest

from opentelemetry.util.genai.stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)


def test_stream_wrapper_abstract_method_signatures_match():
    method_names = (
        "_process_chunk",
        "_on_stream_end",
        "_on_stream_error",
        "_handle_process_chunk_error",
    )

    for method_name in method_names:
        assert inspect.signature(
            getattr(SyncStreamWrapper, method_name)
        ) == inspect.signature(getattr(AsyncStreamWrapper, method_name))


class _FakeSyncStream:
    def __init__(self, chunks=None, error=None, close_error=None):
        self._chunks = list(chunks or [])
        self._error = error
        self._close_error = close_error
        self.close_count = 0
        self.extra_attribute = "passthrough"

    def __iter__(self):
        return self

    def __next__(self):
        if self._chunks:
            return self._chunks.pop(0)
        if self._error:
            raise self._error
        raise StopIteration

    def close(self):
        self.close_count += 1
        if self._close_error:
            raise self._close_error

    def __len__(self):
        return 42


class _FakeSyncIterable:
    def __init__(self, chunks=None):
        self.iterator = iter(chunks or [])
        self.close_count = 0

    def __iter__(self):
        return self.iterator

    def close(self):
        self.close_count += 1


class _TestSyncStreamWrapper(SyncStreamWrapper):
    def __init__(self, stream):
        super().__init__(stream)
        self._self_processed = []
        self._self_stop_count = 0
        self._self_failures = []

    def _process_chunk(self, chunk):
        self._self_processed.append(chunk)

    def _on_stream_end(self):
        self._self_stop_count += 1

    def _on_stream_error(self, error):
        self._self_failures.append(error)


class _FailingSyncProcessStreamWrapper(_TestSyncStreamWrapper):
    def _process_chunk(self, chunk):
        raise ValueError("instrumentation failed")


class _FailingSyncStopStreamWrapper(_TestSyncStreamWrapper):
    def _on_stream_end(self):
        self._self_stop_count += 1
        raise ValueError("instrumentation failed")


class _FailingSyncFailStreamWrapper(_TestSyncStreamWrapper):
    def _on_stream_error(self, error):
        self._self_failures.append(error)
        raise ValueError("instrumentation failed")


def test_sync_stream_wrapper_processes_chunks_and_stops():
    stream = _FakeSyncStream(chunks=["chunk"])
    wrapper = _TestSyncStreamWrapper(stream)

    assert next(wrapper) == "chunk"
    assert wrapper._self_processed == ["chunk"]

    try:
        next(wrapper)
    except StopIteration:
        pass

    assert wrapper._self_stop_count == 1


def test_sync_stream_wrapper_processes_iterables():
    stream = _FakeSyncIterable(chunks=["chunk"])
    wrapper = _TestSyncStreamWrapper(stream)

    assert next(wrapper) == "chunk"
    assert wrapper._self_processed == ["chunk"]

    with pytest.raises(StopIteration):
        next(wrapper)

    assert wrapper._self_stop_count == 1


def test_sync_stream_wrapper_fails_stream_errors():
    error = ValueError("boom")
    wrapper = _TestSyncStreamWrapper(_FakeSyncStream(error=error))

    try:
        next(wrapper)
    except ValueError:
        pass

    assert wrapper._self_failures == [error]


def test_sync_stream_wrapper_close_stops_once():
    stream = _FakeSyncStream(chunks=["chunk"])
    wrapper = _TestSyncStreamWrapper(stream)

    wrapper.close()
    wrapper.close()

    assert stream.close_count == 2
    assert wrapper._self_stop_count == 1
    assert not wrapper._self_failures


def test_sync_stream_wrapper_close_fails_with_close_error():
    error = RuntimeError("close failure")
    wrapper = _TestSyncStreamWrapper(
        _FakeSyncStream(chunks=["chunk"], close_error=error)
    )

    with pytest.raises(RuntimeError, match="close failure"):
        wrapper.close()

    assert wrapper._self_failures == [error]
    assert wrapper._self_stop_count == 0


def test_sync_stream_wrapper_exit_closes_and_propagates_user_errors():
    stream = _FakeSyncStream(chunks=["chunk"])
    wrapper = _TestSyncStreamWrapper(stream)
    error = RuntimeError("user failure")

    assert wrapper.__exit__(RuntimeError, error, None) is False

    assert stream.close_count == 1
    assert wrapper._self_stop_count == 0
    assert wrapper._self_failures == [error]


def test_sync_stream_wrapper_exit_keeps_user_error_when_close_fails():
    close_error = RuntimeError("close failure")
    stream = _FakeSyncStream(chunks=["chunk"], close_error=close_error)
    wrapper = _TestSyncStreamWrapper(stream)
    error = RuntimeError("user failure")

    assert wrapper.__exit__(RuntimeError, error, None) is False

    assert stream.close_count == 1
    assert wrapper._self_failures == [error]
    assert wrapper._self_stop_count == 0


def test_sync_stream_wrapper_swallows_finalize_errors():
    wrapper = _FailingSyncStopStreamWrapper(_FakeSyncStream())

    wrapper.close()
    wrapper.close()

    assert wrapper._self_stop_count == 1


def test_sync_stream_wrapper_swallows_failure_finalize_errors():
    close_error = RuntimeError("close failure")
    stream = _FakeSyncStream(close_error=close_error)
    wrapper = _FailingSyncFailStreamWrapper(stream)

    with pytest.raises(RuntimeError, match="close failure"):
        wrapper.close()
    stream._close_error = None
    wrapper.close()

    assert wrapper._self_failures == [close_error]


def test_sync_stream_wrapper_swallows_stop_iteration_finalize_errors():
    wrapper = _FailingSyncStopStreamWrapper(_FakeSyncStream())

    with pytest.raises(StopIteration):
        next(wrapper)


def test_sync_stream_wrapper_preserves_stream_error_when_finalize_fails():
    error = RuntimeError("stream failure")
    wrapper = _FailingSyncFailStreamWrapper(_FakeSyncStream(error=error))

    with pytest.raises(RuntimeError, match="stream failure"):
        next(wrapper)


def test_sync_stream_wrapper_getattr_passthrough():
    wrapper = _TestSyncStreamWrapper(_FakeSyncStream())

    assert wrapper.extra_attribute == "passthrough"


def test_sync_stream_wrapper_exposes_wrapped_stream():
    stream = _FakeSyncStream()
    wrapper = _TestSyncStreamWrapper(stream)

    assert getattr(wrapper, "__wrapped__") is stream


def test_sync_stream_wrapper_magic_method_passthrough():
    wrapper = _TestSyncStreamWrapper(_FakeSyncStream())

    assert len(wrapper) == 42


def test_sync_stream_wrapper_stop_iteration_does_not_double_finalize():
    wrapper = _TestSyncStreamWrapper(_FakeSyncStream())

    with pytest.raises(StopIteration):
        next(wrapper)
    wrapper.close()

    assert wrapper._self_stop_count == 1
    assert not wrapper._self_failures


def test_sync_stream_wrapper_swallows_process_chunk_errors():
    wrapper = _FailingSyncProcessStreamWrapper(
        _FakeSyncStream(chunks=["chunk"])
    )

    assert next(wrapper) == "chunk"
    assert not wrapper._self_failures


class _FakeAsyncStream:
    def __init__(self, chunks=None, error=None, close_error=None):
        self._chunks = list(chunks or [])
        self._error = error
        self._close_error = close_error
        self.close_count = 0
        self.extra_attribute = "passthrough"

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._chunks:
            return self._chunks.pop(0)
        if self._error:
            raise self._error
        raise StopAsyncIteration

    async def close(self):
        self.close_count += 1
        if self._close_error:
            raise self._close_error

    def __len__(self):
        return 42


class _FakeAsyncIterable:
    def __init__(self, chunks=None):
        self.iterator = _FakeAsyncStream(chunks=chunks)
        self.close_count = 0

    def __aiter__(self):
        return self.iterator

    async def close(self):
        self.close_count += 1


class _TestAsyncStreamWrapper(AsyncStreamWrapper):
    def __init__(self, stream):
        super().__init__(stream)
        self._self_processed = []
        self._self_stop_count = 0
        self._self_failures = []

    def _process_chunk(self, chunk):
        self._self_processed.append(chunk)

    def _on_stream_end(self):
        self._self_stop_count += 1

    def _on_stream_error(self, error):
        self._self_failures.append(error)


class _FailingAsyncProcessStreamWrapper(_TestAsyncStreamWrapper):
    def _process_chunk(self, chunk):
        raise ValueError("instrumentation failed")


class _FailingAsyncStopStreamWrapper(_TestAsyncStreamWrapper):
    def _on_stream_end(self):
        self._self_stop_count += 1
        raise ValueError("instrumentation failed")


class _FailingAsyncFailStreamWrapper(_TestAsyncStreamWrapper):
    def _on_stream_error(self, error):
        self._self_failures.append(error)
        raise ValueError("instrumentation failed")


def test_async_stream_wrapper_processes_chunks_and_stops():
    async def exercise():
        wrapper = _TestAsyncStreamWrapper(_FakeAsyncStream(chunks=["chunk"]))

        assert await anext(wrapper) == "chunk"
        assert wrapper._self_processed == ["chunk"]

        try:
            await anext(wrapper)
        except StopAsyncIteration:
            pass

        assert wrapper._self_stop_count == 1

    asyncio.run(exercise())


def test_async_stream_wrapper_processes_async_iterables():
    async def exercise():
        stream = _FakeAsyncIterable(chunks=["chunk"])
        wrapper = _TestAsyncStreamWrapper(stream)

        assert await anext(wrapper) == "chunk"
        assert wrapper._self_processed == ["chunk"]

        with pytest.raises(StopAsyncIteration):
            await anext(wrapper)

        assert wrapper._self_stop_count == 1

    asyncio.run(exercise())


def test_async_stream_wrapper_fails_stream_errors():
    async def exercise():
        error = ValueError("boom")
        wrapper = _TestAsyncStreamWrapper(_FakeAsyncStream(error=error))

        with pytest.raises(ValueError):
            await anext(wrapper)

        assert wrapper._self_failures == [error]

    asyncio.run(exercise())


def test_async_stream_wrapper_close_stops_once():
    async def exercise():
        stream = _FakeAsyncStream(chunks=["chunk"])
        wrapper = _TestAsyncStreamWrapper(stream)

        await wrapper.close()
        await wrapper.close()

        assert stream.close_count == 2
        assert wrapper._self_stop_count == 1
        assert not wrapper._self_failures

    asyncio.run(exercise())


def test_async_stream_wrapper_close_fails_with_close_error():
    async def exercise():
        error = RuntimeError("close failure")
        wrapper = _TestAsyncStreamWrapper(
            _FakeAsyncStream(chunks=["chunk"], close_error=error)
        )

        with pytest.raises(RuntimeError, match="close failure"):
            await wrapper.close()

        assert wrapper._self_failures == [error]
        assert wrapper._self_stop_count == 0

    asyncio.run(exercise())


def test_async_stream_wrapper_exit_closes_and_propagates_user_errors():
    async def exercise():
        stream = _FakeAsyncStream(chunks=["chunk"])
        wrapper = _TestAsyncStreamWrapper(stream)
        error = RuntimeError("user failure")

        assert await wrapper.__aexit__(RuntimeError, error, None) is False

        assert stream.close_count == 1
        assert wrapper._self_stop_count == 0
        assert wrapper._self_failures == [error]

    asyncio.run(exercise())


def test_async_stream_wrapper_exit_keeps_user_error_when_close_fails():
    async def exercise():
        close_error = RuntimeError("close failure")
        stream = _FakeAsyncStream(chunks=["chunk"], close_error=close_error)
        wrapper = _TestAsyncStreamWrapper(stream)
        error = RuntimeError("user failure")

        assert await wrapper.__aexit__(RuntimeError, error, None) is False

        assert stream.close_count == 1
        assert wrapper._self_failures == [error]
        assert wrapper._self_stop_count == 0

    asyncio.run(exercise())


def test_async_stream_wrapper_swallows_finalize_errors():
    async def exercise():
        wrapper = _FailingAsyncStopStreamWrapper(_FakeAsyncStream())

        await wrapper.close()
        await wrapper.close()

        assert wrapper._self_stop_count == 1

    asyncio.run(exercise())


def test_async_stream_wrapper_swallows_failure_finalize_errors():
    async def exercise():
        close_error = RuntimeError("close failure")
        stream = _FakeAsyncStream(close_error=close_error)
        wrapper = _FailingAsyncFailStreamWrapper(stream)

        with pytest.raises(RuntimeError, match="close failure"):
            await wrapper.close()
        stream._close_error = None
        await wrapper.close()

        assert wrapper._self_failures == [close_error]

    asyncio.run(exercise())


def test_async_stream_wrapper_swallows_stop_iteration_finalize_errors():
    async def exercise():
        wrapper = _FailingAsyncStopStreamWrapper(_FakeAsyncStream())

        with pytest.raises(StopAsyncIteration):
            await anext(wrapper)

    asyncio.run(exercise())


def test_async_stream_wrapper_preserves_stream_error_when_finalize_fails():
    async def exercise():
        error = RuntimeError("stream failure")
        wrapper = _FailingAsyncFailStreamWrapper(_FakeAsyncStream(error=error))

        with pytest.raises(RuntimeError, match="stream failure"):
            await anext(wrapper)

    asyncio.run(exercise())


def test_async_stream_wrapper_getattr_passthrough():
    wrapper = _TestAsyncStreamWrapper(_FakeAsyncStream())

    assert wrapper.extra_attribute == "passthrough"


def test_async_stream_wrapper_exposes_wrapped_stream():
    stream = _FakeAsyncStream()
    wrapper = _TestAsyncStreamWrapper(stream)

    assert getattr(wrapper, "__wrapped__") is stream


def test_async_stream_wrapper_magic_method_passthrough():
    wrapper = _TestAsyncStreamWrapper(_FakeAsyncStream())

    assert len(wrapper) == 42


def test_async_stream_wrapper_stop_iteration_does_not_double_finalize():
    async def exercise():
        wrapper = _TestAsyncStreamWrapper(_FakeAsyncStream())

        with pytest.raises(StopAsyncIteration):
            await anext(wrapper)
        await wrapper.close()

        assert wrapper._self_stop_count == 1
        assert not wrapper._self_failures

    asyncio.run(exercise())


def test_async_stream_wrapper_swallows_process_chunk_errors():
    async def exercise():
        wrapper = _FailingAsyncProcessStreamWrapper(
            _FakeAsyncStream(chunks=["chunk"])
        )

        assert await anext(wrapper) == "chunk"
        assert not wrapper._self_failures

    asyncio.run(exercise())
