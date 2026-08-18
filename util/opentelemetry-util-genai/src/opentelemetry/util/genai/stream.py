# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    AsyncIterable,
    Generic,
    Iterable,
    Literal,
    Protocol,
    TypeVar,
)

if TYPE_CHECKING:

    class _ObjectProxy:
        def __init__(self, wrapped: object) -> None: ...

else:
    from wrapt import ObjectProxy as _ObjectProxy


ChunkT = TypeVar("ChunkT")
_ChunkT_co = TypeVar("_ChunkT_co", covariant=True)
_logger = logging.getLogger(__name__)


class _StreamWrapperMeta(ABCMeta, type(_ObjectProxy)):
    """Metaclass compatible with wrapt's proxy type and ABC hooks."""


class _SyncStream(Iterable[_ChunkT_co], Protocol[_ChunkT_co]):
    """Structural type for streams accepted by ``SyncStreamWrapper``."""

    def close(self) -> None: ...


class _AsyncStream(AsyncIterable[_ChunkT_co], Protocol[_ChunkT_co]):
    """Structural type for streams accepted by ``AsyncStreamWrapper``."""

    async def close(self) -> None: ...


class SyncStreamWrapper(
    _ObjectProxy,
    Generic[ChunkT],
    metaclass=_StreamWrapperMeta,
):
    """Base class for synchronous instrumented stream wrappers.

    Subclass this when wrapping a provider SDK stream that is consumed with
    normal iteration. The subclass should pass the SDK stream to
    ``super().__init__(stream)`` and implement the three telemetry hooks:
    ``_process_chunk`` for per-chunk state, ``_on_stream_end`` for successful
    finalization, and ``_on_stream_error`` for failure finalization.

    Users should consume subclasses as normal streams, for example with
    ``for chunk in wrapper`` or ``with wrapper``. The hook methods are called
    internally by the wrapper lifecycle and are not part of the public API.
    """

    def __init__(self, stream: _SyncStream[ChunkT]):
        super().__init__(stream)
        self._self_stream = stream
        self._self_iterator = iter(stream)
        self._self_finalized = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_val is not None:
            self._safe_finalize_failure(exc_val)
            try:
                self._self_stream.close()
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
            self._self_stream.close()
        except Exception as error:
            self._safe_finalize_failure(error)
            raise
        self._safe_finalize_success()

    def __iter__(self):
        # Override ``ObjectProxy.__iter__`` so iteration drives ``__next__``
        # below and runs ``_process_chunk`` per chunk; otherwise iteration
        # would be forwarded to the wrapped stream and bypass instrumentation.
        return self

    def __next__(self) -> ChunkT:
        try:
            chunk = next(self._self_iterator)
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

    def _finalize_success(self) -> None:
        if self._self_finalized:
            return
        self._self_finalized = True
        self._on_stream_end()

    def _finalize_failure(self, error: BaseException) -> None:
        if self._self_finalized:
            return
        self._self_finalized = True
        self._on_stream_error(error)

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
    def _on_stream_end(self) -> None:
        """Finalize the stream successfully."""

    @abstractmethod
    def _on_stream_error(self, error: BaseException) -> None:
        """Finalize the stream with failure."""

    @staticmethod
    def _handle_process_chunk_error(_error: Exception) -> None:
        _logger.debug(
            "GenAI stream instrumentation error during chunk processing",
            exc_info=True,
        )


class AsyncStreamWrapper(
    _ObjectProxy,
    Generic[ChunkT],
    metaclass=_StreamWrapperMeta,
):
    """Base class for asynchronous instrumented stream wrappers.

    Subclass this when wrapping a provider SDK stream that is consumed with
    async iteration. The subclass should pass the SDK stream to
    ``super().__init__(stream)`` and implement the three telemetry hooks:
    ``_process_chunk`` for per-chunk state, ``_on_stream_end`` for successful
    finalization, and ``_on_stream_error`` for failure finalization.

    Users should consume subclasses as normal async streams, for example with
    ``async for chunk in wrapper`` or ``async with wrapper``. The hook methods
    remain synchronous telemetry hooks; async stream reads and close handling
    are owned by this base class.
    """

    def __init__(self, stream: _AsyncStream[ChunkT]):
        super().__init__(stream)
        self._self_stream = stream
        self._self_aiter = aiter(stream)
        self._self_finalized = False

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_val is not None:
            self._safe_finalize_failure(exc_val)
            try:
                await self._self_stream.close()
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug(
                    "GenAI stream close error after user exception",
                    exc_info=True,
                )
            return False

        await self.close()
        return False

    async def close(self) -> None:
        # Named ``close`` (not ``aclose``) to match OpenAI's ``AsyncStream``.
        # Revisit when migrating SDKs that expose ``aclose`` instead.
        try:
            await self._self_stream.close()
        except Exception as error:
            self._safe_finalize_failure(error)
            raise
        self._safe_finalize_success()

    def __aiter__(self):
        # Override ``ObjectProxy.__aiter__`` so iteration drives ``__anext__``
        # below and runs ``_process_chunk`` per chunk; otherwise iteration
        # would be forwarded to the wrapped stream and bypass instrumentation.
        return self

    async def __anext__(self) -> ChunkT:
        try:
            chunk = await anext(self._self_aiter)
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

    def _finalize_success(self) -> None:
        if self._self_finalized:
            return
        self._self_finalized = True
        self._on_stream_end()

    def _finalize_failure(self, error: BaseException) -> None:
        if self._self_finalized:
            return
        self._self_finalized = True
        self._on_stream_error(error)

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
    def _on_stream_end(self) -> None:
        """Finalize the stream successfully."""

    @abstractmethod
    def _on_stream_error(self, error: BaseException) -> None:
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
