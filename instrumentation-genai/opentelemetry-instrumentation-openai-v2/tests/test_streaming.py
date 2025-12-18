# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Contract tests for the streaming wrappers.

These intentionally stay small and focus on behavior we rely on:
- wrappers preserve iteration semantics
- close() is best-effort and does not crash if close is missing
- async stream close is scheduled (and not left un-awaited)
- deprecated StreamWrapper still works and warns
"""

import asyncio
import warnings
from types import SimpleNamespace
from typing import Any, AsyncIterator, Iterator, Optional, cast
from unittest.mock import MagicMock

import pytest

from opentelemetry._logs import Logger
from opentelemetry.trace import Span

import opentelemetry.instrumentation.openai_v2.streaming as streaming_mod
from opentelemetry.instrumentation.openai_v2.streaming import (
    AsyncStreamWrapper,
    StreamWrapper,
    SyncStreamWrapper,
)


def _mock_span() -> Span:
    span = MagicMock(spec=Span)
    span.is_recording.return_value = True
    return span


def _mock_logger() -> Logger:
    return MagicMock(spec=Logger)


class _Chunk:
    """Minimal chunk shape for StreamWrapperBase._process_chunk."""

    def __init__(
        self,
        chunk_id: str = "chunk-1",
        model: str = "gpt-4o",
        choices: Optional[list[Any]] = None,
    ):
        self.id = chunk_id
        self.model = model
        self.choices = choices
        self.service_tier = None
        self.usage = None


def test_sync_wrapper_delegates_iteration():
    chunks = [_Chunk("c1"), _Chunk("c2"), _Chunk("c3")]

    class _SyncStream:
        def __init__(self, items: list[Any]):
            self._it = iter(items)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self._it)

    wrapper = SyncStreamWrapper(
        cast(Iterator[Any], _SyncStream(chunks)),
        _mock_span(),
        _mock_logger(),
        capture_content=False,
    )

    collected = list(wrapper)
    assert [c.id for c in collected] == ["c1", "c2", "c3"]


@pytest.mark.parametrize("has_close", [True, False])
def test_sync_wrapper_close_is_best_effort(has_close: bool):
    class _SyncStream:
        def __init__(self):
            self.closed = False
            self._it = iter([_Chunk("c1")])

        def __iter__(self):
            return self

        def __next__(self):
            return next(self._it)

        if has_close:

            def close(self):
                self.closed = True

    stream = _SyncStream()
    wrapper = SyncStreamWrapper(
        cast(Iterator[Any], stream),
        _mock_span(),
        _mock_logger(),
        capture_content=False,
    )

    wrapper.close()
    assert stream.closed is has_close


@pytest.mark.asyncio
async def test_async_wrapper_close_schedules_close_coroutine(monkeypatch):
    class _AsyncStream:
        def __init__(self):
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def close(self):
            self.closed = True

    stream = _AsyncStream()
    wrapper = AsyncStreamWrapper(
        cast(AsyncIterator[Any], stream),
        _mock_span(),
        _mock_logger(),
        capture_content=False,
    )

    real_loop = asyncio.get_running_loop()
    created_tasks: list[asyncio.Task[Any]] = []

    def _create_task_spy(coro):
        task = real_loop.create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(
        streaming_mod.asyncio,
        "get_running_loop",
        lambda: SimpleNamespace(create_task=_create_task_spy),
    )

    wrapper.close()

    assert len(created_tasks) == 1
    await created_tasks[0]
    assert stream.closed is True


def test_stream_wrapper_deprecated_sync_still_iterates_and_warns():
    class _SyncStream:
        def __init__(self):
            self._it = iter([_Chunk("c1"), _Chunk("c2")])

        def __iter__(self):
            return self

        def __next__(self):
            return next(self._it)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        wrapper = StreamWrapper(
            _SyncStream(),
            _mock_span(),
            _mock_logger(),
            capture_content=False,
        )

        collected = list(wrapper)
        assert [c.id for c in collected] == ["c1", "c2"]

        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)
        assert "StreamWrapper is deprecated" in str(caught[0].message)


@pytest.mark.asyncio
async def test_stream_wrapper_deprecated_async_still_iterates():
    class _AsyncStream:
        def __init__(self):
            self._it = iter([_Chunk("c1"), _Chunk("c2")])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        wrapper = StreamWrapper(
            _AsyncStream(),
            _mock_span(),
            _mock_logger(),
            capture_content=False,
        )

    collected: list[Any] = []
    async for chunk in wrapper:
        collected.append(chunk)
    assert [c.id for c in collected] == ["c1", "c2"]
