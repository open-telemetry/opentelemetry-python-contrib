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
from contextlib import AsyncExitStack, ExitStack, contextmanager
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Callable,
    Generator,
    Generic,
    Iterator,
    Protocol,
    TypeVar,
    cast,
)

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    LLMInvocation,
)

from .messages_extractors import set_invocation_response_attributes

try:
    from anthropic.lib.streaming._messages import (  # pylint: disable=no-name-in-module
        accumulate_event as _sdk_accumulate_event,
    )
except ImportError:
    _sdk_accumulate_event = None

if TYPE_CHECKING:
    from anthropic.lib.streaming._messages import (  # pylint: disable=no-name-in-module
        AsyncMessageStreamManager,
        MessageStreamManager,
    )
    from anthropic.lib.streaming._types import (  # pylint: disable=no-name-in-module
        MessageStreamEvent,
    )
    from anthropic.types import (
        Message,
        RawMessageStreamEvent,
    )


_logger = logging.getLogger(__name__)
SyncResponseT = TypeVar("SyncResponseT", bound="_SupportsClose")
AsyncResponseT = TypeVar("AsyncResponseT", bound="_SupportsAclose")
StreamEventT = TypeVar(
    "StreamEventT", "RawMessageStreamEvent", "MessageStreamEvent"
)
StreamEventT_co = TypeVar(
    "StreamEventT_co",
    "RawMessageStreamEvent",
    "MessageStreamEvent",
    covariant=True,
)
accumulate_event = cast("Callable[..., Message] | None", _sdk_accumulate_event)


class _SupportsClose(Protocol):
    def close(self) -> None: ...


class _SupportsAclose(_SupportsClose, Protocol):
    async def aclose(self) -> None: ...


class _SyncStream(Protocol[StreamEventT_co]):
    @property
    def response(self) -> _SupportsClose: ...

    def __iter__(self) -> Iterator[StreamEventT_co]: ...

    def __next__(self) -> StreamEventT_co: ...

    def close(self) -> None: ...


class _AsyncStream(Protocol[StreamEventT_co]):
    @property
    def response(self) -> _SupportsAclose: ...

    def __aiter__(self) -> AsyncIterator[StreamEventT_co]: ...

    async def __anext__(self) -> StreamEventT_co: ...

    async def close(self) -> None: ...


def _set_response_attributes(
    invocation: LLMInvocation,
    result: "Message | None",
    capture_content: bool,
) -> None:
    set_invocation_response_attributes(invocation, result, capture_content)


class _ResponseProxy(Generic[SyncResponseT]):
    def __init__(self, response: SyncResponseT, finalize: Callable[[], None]):
        self._response = response
        self._finalize = finalize

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._finalize()

    def __getattr__(self, name: str):
        return getattr(self._response, name)


class _AsyncResponseProxy(Generic[AsyncResponseT]):
    def __init__(self, response: AsyncResponseT, finalize: Callable[[], None]):
        self._response = response
        self._finalize = finalize

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._finalize()

    async def aclose(self) -> None:
        try:
            await self._response.aclose()
        finally:
            self._finalize()

    def __getattr__(self, name: str):
        return getattr(self._response, name)


class MessageWrapper:
    """Wrapper for non-streaming Message response that handles telemetry."""

    def __init__(self, message: Message, capture_content: bool):
        self._message = message
        self._capture_content = capture_content

    def extract_into(self, invocation: LLMInvocation) -> None:
        """Extract response data into the invocation."""
        set_invocation_response_attributes(
            invocation, self._message, self._capture_content
        )

    @property
    def message(self) -> Message:
        """Return the wrapped Message object."""
        return self._message


class MessagesStreamWrapper(Generic[StreamEventT], Iterator[StreamEventT]):
    """Wrapper for Anthropic Stream that handles telemetry."""

    def __init__(
        self,
        stream: _SyncStream[StreamEventT],
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self._message: "Message | None" = None
        self._capture_content = capture_content
        self._finalized = False

    def __enter__(self) -> "MessagesStreamWrapper[StreamEventT]":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            if exc_type is not None:
                self._fail(
                    str(exc_val), type(exc_val) if exc_val else Exception
                )
        finally:
            self.close()
        return False

    def close(self) -> None:
        try:
            self.stream.close()
        finally:
            self._stop()

    def __iter__(self) -> "MessagesStreamWrapper[StreamEventT]":
        return self

    def __next__(self) -> StreamEventT:
        try:
            chunk = next(self.stream)
        except StopIteration:
            self._stop()
            raise
        except Exception as exc:
            self._fail(str(exc), type(exc))
            raise
        with self._safe_instrumentation("stream chunk processing"):
            self._process_chunk(chunk)
        return chunk

    def __getattr__(self, name: str) -> object:
        return getattr(self.stream, name)

    @property
    def response(
        self,
    ) -> "_ResponseProxy[_SupportsClose] | _AsyncResponseProxy[_SupportsAclose] | None":
        return _ResponseProxy(self.stream.response, self._stop)

    def _stop(self) -> None:
        if self._finalized:
            return
        with self._safe_instrumentation("response attribute extraction"):
            _set_response_attributes(
                self.invocation, self._message, self._capture_content
            )
        with self._safe_instrumentation("stop_llm"):
            self.handler.stop_llm(self.invocation)
        self._finalized = True

    def _fail(self, message: str, error_type: type[BaseException]) -> None:
        if self._finalized:
            return
        with self._safe_instrumentation("fail_llm"):
            self.handler.fail_llm(
                self.invocation, Error(message=message, type=error_type)
            )
        self._finalized = True

    @staticmethod
    @contextmanager
    def _safe_instrumentation(
        context: str,
    ) -> Generator[None, None, None]:
        try:
            yield
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "Anthropic MessagesStreamWrapper instrumentation error in %s",
                context,
                exc_info=True,
            )

    def _process_chunk(self, chunk: StreamEventT) -> None:
        """Accumulate a final message snapshot from a streaming chunk."""
        snapshot = cast(
            "Message | None",
            getattr(self.stream, "current_message_snapshot", None),
        )
        if snapshot is not None:
            self._message = snapshot
            return
        if accumulate_event is None:
            return
        self._message = accumulate_event(
            event=cast("RawMessageStreamEvent", chunk),
            current_snapshot=self._message,
        )


class AsyncMessagesStreamWrapper(MessagesStreamWrapper[StreamEventT]):
    """Wrapper for async Anthropic Stream that handles telemetry."""

    stream: _AsyncStream[StreamEventT]

    def __init__(
        self,
        stream: _AsyncStream[StreamEventT],
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self._message: "Message | None" = None
        self._capture_content = capture_content
        self._finalized = False

    async def __aenter__(self) -> "AsyncMessagesStreamWrapper[StreamEventT]":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            if exc_type is not None:
                self._fail(
                    str(exc_val), type(exc_val) if exc_val else Exception
                )
        finally:
            await self.close()
        return False

    async def close(self) -> None:  # type: ignore[override]
        try:
            await self.stream.close()
        finally:
            self._stop()

    def __aiter__(self) -> "AsyncMessagesStreamWrapper[StreamEventT]":
        return self

    @property
    def response(
        self,
    ) -> "_ResponseProxy[_SupportsClose] | _AsyncResponseProxy[_SupportsAclose] | None":
        return _AsyncResponseProxy(self.stream.response, self._stop)

    async def __anext__(self) -> StreamEventT:
        try:
            chunk = await self.stream.__anext__()
        except StopAsyncIteration:
            self._stop()
            raise
        except Exception as exc:
            self._fail(str(exc), type(exc))
            raise
        with self._safe_instrumentation("stream chunk processing"):
            self._process_chunk(chunk)
        return chunk


class MessagesStreamManagerWrapper:
    """Wrapper for sync Anthropic stream managers."""

    def __init__(
        self,
        manager: "MessageStreamManager",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: (
            MessagesStreamWrapper[MessageStreamEvent] | None
        ) = None

    def __enter__(self) -> MessagesStreamWrapper[MessageStreamEvent]:
        stream = cast(
            "_SyncStream[MessageStreamEvent]",
            self._manager.__enter__(),
        )
        self._stream_wrapper = MessagesStreamWrapper(
            stream,
            self._handler,
            self._invocation,
            self._capture_content,
        )
        return self._stream_wrapper

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        suppressed = False
        stream_wrapper = self._stream_wrapper
        self._stream_wrapper = None
        with ExitStack() as cleanup:
            if stream_wrapper is not None:

                def finalize_stream_wrapper() -> None:
                    if suppressed:
                        stream_wrapper.__exit__(None, None, None)
                    else:
                        stream_wrapper.__exit__(exc_type, exc_val, exc_tb)

                cleanup.callback(finalize_stream_wrapper)
            suppressed = self._manager.__exit__(exc_type, exc_val, exc_tb)
            return suppressed

    def __getattr__(self, name: str) -> object:
        return getattr(self._manager, name)


class AsyncMessagesStreamManagerWrapper:
    """Wrapper for AsyncMessageStreamManager that handles telemetry.

    Wraps AsyncMessageStreamManager from the Anthropic SDK:
    https://github.com/anthropics/anthropic-sdk-python/blob/05220bc1c1079fe01f5c4babc007ec7a990859d9/src/anthropic/lib/streaming/_messages.py#L294
    """

    def __init__(
        self,
        manager: "AsyncMessageStreamManager",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: (
            AsyncMessagesStreamWrapper[MessageStreamEvent] | None
        ) = None

    async def __aenter__(
        self,
    ) -> AsyncMessagesStreamWrapper[MessageStreamEvent]:
        msg_stream = cast(
            "_AsyncStream[MessageStreamEvent]",
            await self._manager.__aenter__(),
        )
        self._stream_wrapper = AsyncMessagesStreamWrapper(
            msg_stream,
            self._handler,
            self._invocation,
            self._capture_content,
        )
        return self._stream_wrapper

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        suppressed = False
        stream_wrapper = self._stream_wrapper
        self._stream_wrapper = None
        async with AsyncExitStack() as cleanup:
            if stream_wrapper is not None:

                async def finalize_stream_wrapper() -> None:
                    if suppressed:
                        await stream_wrapper.__aexit__(None, None, None)
                    else:
                        await stream_wrapper.__aexit__(
                            exc_type, exc_val, exc_tb
                        )

                cleanup.push_async_callback(finalize_stream_wrapper)
            suppressed = await self._manager.__aexit__(
                exc_type, exc_val, exc_tb
            )
            return suppressed

    def __getattr__(self, name: str) -> object:
        return getattr(self._manager, name)
