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

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any, Generic, Literal, TypeVar

ChunkT = TypeVar("ChunkT")
_logger = logging.getLogger(__name__)


class SyncStreamWrapper(ABC, Generic[ChunkT]):
    """Base class for synchronous instrumented stream wrappers.

    Subclass this when wrapping a provider SDK stream that is consumed with
    normal iteration. The subclass should pass the SDK stream to
    ``super().__init__(stream)`` and implement the three telemetry hooks:
    ``_process_chunk`` for per-chunk state, ``_stop_stream`` for successful
    finalization, and ``_fail_stream`` for failure finalization.

    Users should consume subclasses as normal streams, for example with
    ``for chunk in wrapper`` or ``with wrapper``. The hook methods are called
    internally by the wrapper lifecycle and are not part of the public API.
    """

    def __init__(self, stream: Any):
        self.stream = stream
        self._iterator = iter(stream)
        self._finalized = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is not None:
            self._safe_finalize_failure(exc_val or Exception())
            try:
                self.stream.close()
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug(
                    "GenAI stream close error after user exception",
                    exc_info=True,
                )
            return False

        self.close()
        return False

    def close(self) -> None:
        try:
            self.stream.close()
        except Exception as error:
            self._safe_finalize_failure(error)
            raise
        self._safe_finalize_success()

    def __iter__(self):
        return self

    def __next__(self) -> ChunkT:
        try:
            chunk = next(self._iterator)
        except StopIteration:
            self._safe_finalize_success()
            raise
        except Exception as error:
            self._safe_finalize_failure(error)
            raise
        try:
            self._process_chunk(chunk)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._handle_process_chunk_error(error)
        return chunk

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)

    def _finalize_success(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._stop_stream()

    def _finalize_failure(self, error: BaseException) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._fail_stream(error)

    def _safe_finalize_success(self) -> None:
        try:
            self._finalize_success()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "GenAI stream instrumentation error during finalization",
                exc_info=True,
            )

    def _safe_finalize_failure(self, error: BaseException) -> None:
        try:
            self._finalize_failure(error)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "GenAI stream instrumentation error during failure finalization",
                exc_info=True,
            )

    @abstractmethod
    def _process_chunk(self, chunk: ChunkT) -> None:
        """Process one stream chunk for telemetry."""

    @abstractmethod
    def _stop_stream(self) -> None:
        """Finalize the stream successfully."""

    @abstractmethod
    def _fail_stream(self, error: BaseException) -> None:
        """Finalize the stream with failure."""

    @staticmethod
    def _handle_process_chunk_error(_error: Exception) -> None:
        _logger.debug(
            "GenAI stream instrumentation error during chunk processing",
            exc_info=True,
        )


class AsyncStreamWrapper(ABC, Generic[ChunkT]):
    """Base class for asynchronous instrumented stream wrappers.

    Subclass this when wrapping a provider SDK stream that is consumed with
    async iteration. The subclass should pass the SDK stream to
    ``super().__init__(stream)`` and implement the three telemetry hooks:
    ``_process_chunk`` for per-chunk state, ``_stop_stream`` for successful
    finalization, and ``_fail_stream`` for failure finalization.

    Users should consume subclasses as normal async streams, for example with
    ``async for chunk in wrapper`` or ``async with wrapper``. The hook methods
    remain synchronous telemetry hooks; async stream reads and close handling
    are owned by this base class.
    """

    def __init__(self, stream: Any):
        self.stream = stream
        self._aiter = aiter(stream)
        self._finalized = False

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is not None:
            self._safe_finalize_failure(exc_val or Exception())
            try:
                await self.stream.close()
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug(
                    "GenAI stream close error after user exception",
                    exc_info=True,
                )
            return False

        await self.close()
        return False

    async def close(self) -> None:
        try:
            await self.stream.close()
        except Exception as error:
            self._safe_finalize_failure(error)
            raise
        self._safe_finalize_success()

    def __aiter__(self):
        return self

    async def __anext__(self) -> ChunkT:
        try:
            chunk = await anext(self._aiter)
        except StopAsyncIteration:
            self._safe_finalize_success()
            raise
        except Exception as error:
            self._safe_finalize_failure(error)
            raise
        try:
            self._process_chunk(chunk)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._handle_process_chunk_error(error)
        return chunk

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)

    def _finalize_success(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._stop_stream()

    def _finalize_failure(self, error: BaseException) -> None:
        if self._finalized:
            return
        self._finalized = True
        self._fail_stream(error)

    def _safe_finalize_success(self) -> None:
        try:
            self._finalize_success()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "GenAI stream instrumentation error during finalization",
                exc_info=True,
            )

    def _safe_finalize_failure(self, error: BaseException) -> None:
        try:
            self._finalize_failure(error)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "GenAI stream instrumentation error during failure finalization",
                exc_info=True,
            )

    @abstractmethod
    def _process_chunk(self, chunk: ChunkT) -> None:
        """Process one stream chunk for telemetry."""

    @abstractmethod
    def _stop_stream(self) -> None:
        """Finalize the stream successfully."""

    @abstractmethod
    def _fail_stream(self, error: BaseException) -> None:
        """Finalize the stream with failure."""

    @staticmethod
    def _handle_process_chunk_error(_error: Exception) -> None:
        _logger.debug(
            "GenAI stream instrumentation error during chunk processing",
            exc_info=True,
        )


__all__ = [
    "AsyncStreamWrapper",
    "SyncStreamWrapper",
]
