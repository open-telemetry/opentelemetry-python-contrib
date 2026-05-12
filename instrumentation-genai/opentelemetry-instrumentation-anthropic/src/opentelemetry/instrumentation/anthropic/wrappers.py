# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Iterator,
    TypeVar,
    cast,
)

from .messages_extractors import set_invocation_response_attributes

try:
    from anthropic.lib.streaming._messages import (  # pylint: disable=no-name-in-module
        accumulate_event as _sdk_accumulate_event,
    )
except ImportError:
    _sdk_accumulate_event = None

if TYPE_CHECKING:
    from anthropic._streaming import AsyncStream, Stream
    from anthropic.lib.streaming._messages import (  # pylint: disable=no-name-in-module
        AsyncMessageStream,
        AsyncMessageStreamManager,
        MessageStream,
        MessageStreamManager,
    )
    from anthropic.lib.streaming._types import (  # pylint: disable=no-name-in-module
        ParsedMessageStreamEvent,
    )
    from anthropic.types import (
        Message,
        RawMessageStreamEvent,
    )
    from anthropic.types.parsed_message import ParsedMessage

    from opentelemetry.util.genai.invocation import InferenceInvocation


ResponseT = TypeVar("ResponseT")
ResponseFormatT = TypeVar("ResponseFormatT")
accumulate_event = cast("Callable[..., Message] | None", _sdk_accumulate_event)


def _set_response_attributes(
    invocation: InferenceInvocation,
    result: Message | None,
    capture_content: bool,
) -> None:
    set_invocation_response_attributes(invocation, result, capture_content)


class _ResponseProxy(Generic[ResponseT]):
    def __init__(self, response: ResponseT, finalize: Callable[[], None]):
        self._response: Any = response
        self._finalize = finalize

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._finalize()

    def __getattr__(self, name: str):
        return getattr(self._response, name)


class _AsyncResponseProxy(Generic[ResponseT]):
    def __init__(self, response: ResponseT, finalize: Callable[[], None]):
        self._response: Any = response
        self._finalize = finalize

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

    def extract_into(self, invocation: InferenceInvocation) -> None:
        """Extract response data into the invocation."""
        set_invocation_response_attributes(
            invocation, self._message, self._capture_content
        )

    @property
    def message(self) -> Message:
        """Return the wrapped Message object."""
        return self._message


class MessagesStreamWrapper(
    Generic[ResponseFormatT],
    Iterator[
        "RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]"
    ],
):
    """Wrapper for Anthropic Stream that handles telemetry."""

    def __init__(
        self,
        stream: Stream[RawMessageStreamEvent] | MessageStream[ResponseFormatT],
        invocation: InferenceInvocation,
        capture_content: bool,
    ):
        self.stream = stream
        self.invocation = invocation
        self._message: Message | ParsedMessage[ResponseFormatT] | None = None
        self._capture_content = capture_content
        self._finalized = False

    def __enter__(self) -> MessagesStreamWrapper[ResponseFormatT]:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            if exc_val is not None:
                self._fail(exc_val)
        finally:
            self.close()
        return False

    def close(self) -> None:
        try:
            self.stream.close()
        except Exception as exc:
            self._fail(exc)
            raise
        self._stop()

    def __iter__(self) -> MessagesStreamWrapper[ResponseFormatT]:
        return self

    def __next__(
        self,
    ) -> RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]:
        try:
            chunk = next(self.stream)
        except StopIteration:
            self._stop()
            raise
        except Exception as exc:
            self._fail(exc)
            raise
        self._process_chunk(chunk)
        return chunk

    def __getattr__(self, name: str) -> object:
        return getattr(self.stream, name)

    @property
    def response(self):
        return _ResponseProxy(self.stream.response, self._stop)

    def _stop(self) -> None:
        if self._finalized:
            return
        _set_response_attributes(
            self.invocation, self._message, self._capture_content
        )
        self.invocation.stop()
        self._finalized = True

    def _fail(self, exc: BaseException) -> None:
        if self._finalized:
            return
        self.invocation.fail(exc)
        self._finalized = True

    def _process_chunk(
        self,
        chunk: RawMessageStreamEvent
        | ParsedMessageStreamEvent[ResponseFormatT],
    ) -> None:
        """Accumulate a final message snapshot from a streaming chunk."""
        snapshot = cast(
            "ParsedMessage[ResponseFormatT] | None",
            getattr(self.stream, "current_message_snapshot", None),
        )
        if snapshot is not None:
            self._message = snapshot
            return
        if accumulate_event is None:
            return
        self._message = accumulate_event(
            event=cast("RawMessageStreamEvent", chunk),
            current_snapshot=cast(
                "ParsedMessage[ResponseFormatT] | None", self._message
            ),
        )


class AsyncMessagesStreamWrapper(MessagesStreamWrapper[ResponseFormatT]):
    """Wrapper for async Anthropic Stream that handles telemetry."""

    def __init__(
        self,
        stream: AsyncStream[RawMessageStreamEvent]
        | AsyncMessageStream[ResponseFormatT],
        invocation: InferenceInvocation,
        capture_content: bool,
    ):
        self.stream = stream
        self.invocation = invocation
        self._message: Message | ParsedMessage[ResponseFormatT] | None = None
        self._capture_content = capture_content
        self._finalized = False

    async def __aenter__(
        self,
    ) -> AsyncMessagesStreamWrapper[ResponseFormatT]:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            if exc_val is not None:
                self._fail(exc_val)
        finally:
            await self.close()
        return False

    async def close(self) -> None:  # type: ignore[override]
        try:
            await self.stream.close()
        except Exception as exc:
            self._fail(exc)
            raise
        self._stop()

    def __aiter__(self) -> AsyncMessagesStreamWrapper[ResponseFormatT]:
        return self

    @property
    def response(self) -> Any:
        return _AsyncResponseProxy(self.stream.response, self._stop)

    async def __anext__(
        self,
    ) -> RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]:
        try:
            chunk = await self.stream.__anext__()
        except StopAsyncIteration:
            self._stop()
            raise
        except Exception as exc:
            self._fail(exc)
            raise
        self._process_chunk(chunk)
        return chunk


class MessagesStreamManagerWrapper(Generic[ResponseFormatT]):
    """Wrapper for sync Anthropic stream managers."""

    def __init__(
        self,
        manager: MessageStreamManager[ResponseFormatT],
        invocation_factory: Callable[[], InferenceInvocation],
        capture_content: bool,
    ):
        self._manager = manager
        self._invocation_factory = invocation_factory
        self._invocation: InferenceInvocation | None = None
        self._capture_content = capture_content
        self._stream_wrapper: MessagesStreamWrapper[ResponseFormatT] | None = (
            None
        )

    def __enter__(self) -> MessagesStreamWrapper[ResponseFormatT]:
        invocation = self._invocation_factory()
        self._invocation = invocation
        try:
            stream = self._manager.__enter__()
        except Exception as exc:
            invocation.fail(exc)
            raise
        self._stream_wrapper = MessagesStreamWrapper(
            stream,
            invocation,
            self._capture_content,
        )
        return self._stream_wrapper

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        stream_wrapper = self._stream_wrapper
        self._stream_wrapper = None
        try:
            suppressed = self._manager.__exit__(exc_type, exc_val, exc_tb)
        except Exception as exc:
            if stream_wrapper is not None:
                stream_wrapper.__exit__(type(exc), exc, exc.__traceback__)
            elif self._invocation is not None:
                self._invocation.fail(exc)
            raise
        if stream_wrapper is not None:
            if suppressed:
                stream_wrapper.__exit__(None, None, None)
            else:
                stream_wrapper.__exit__(exc_type, exc_val, exc_tb)
        return suppressed

    def __getattr__(self, name: str) -> object:
        return getattr(self._manager, name)


class AsyncMessagesStreamManagerWrapper(Generic[ResponseFormatT]):
    """Wrapper for AsyncMessageStreamManager that handles telemetry.

    Wraps AsyncMessageStreamManager from the Anthropic SDK:
    https://github.com/anthropics/anthropic-sdk-python/blob/05220bc1c1079fe01f5c4babc007ec7a990859d9/src/anthropic/lib/streaming/_messages.py#L294
    """

    # When async Messages.stream() instrumentation is wired up, start the
    # invocation lazily in __aenter__ to avoid opening spans for unentered
    # managers.

    def __init__(
        self,
        manager: AsyncMessageStreamManager[ResponseFormatT],
        invocation: InferenceInvocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: (
            AsyncMessagesStreamWrapper[ResponseFormatT] | None
        ) = None

    async def __aenter__(
        self,
    ) -> AsyncMessagesStreamWrapper[ResponseFormatT]:
        try:
            msg_stream = await self._manager.__aenter__()
        except Exception as exc:
            self._invocation.fail(exc)
            raise
        self._stream_wrapper = AsyncMessagesStreamWrapper(
            msg_stream,
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
        stream_wrapper = self._stream_wrapper
        self._stream_wrapper = None
        try:
            suppressed = await self._manager.__aexit__(
                exc_type, exc_val, exc_tb
            )
        except Exception as exc:
            if stream_wrapper is not None:
                await stream_wrapper.__aexit__(
                    type(exc), exc, exc.__traceback__
                )
            else:
                self._invocation.fail(exc)
            raise
        if stream_wrapper is not None:
            if suppressed:
                await stream_wrapper.__aexit__(None, None, None)
            else:
                await stream_wrapper.__aexit__(exc_type, exc_val, exc_tb)
        return suppressed

    def __getattr__(self, name: str) -> object:
        return getattr(self._manager, name)
