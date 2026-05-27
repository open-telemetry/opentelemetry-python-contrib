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
    Any,
    Callable,
    Generator,
    Generic,
    Iterator,
    TypeVar,
    cast,
)

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    LLMInvocation,
)

from .messages_extractors import (
    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
    set_invocation_response_attributes,
)

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


_logger = logging.getLogger(__name__)
ResponseT = TypeVar("ResponseT")
ResponseFormatT = TypeVar("ResponseFormatT")
accumulate_event = cast("Callable[..., Message] | None", _sdk_accumulate_event)


def _set_response_attributes(
    invocation: LLMInvocation,
    result: "Message | None",
    capture_content: bool,
) -> None:
    set_invocation_response_attributes(invocation, result, capture_content)


def _get_usage_input_tokens(usage: object) -> int | None:
    input_tokens = getattr(usage, "input_tokens", None)
    cache_creation_input_tokens = getattr(
        usage, "cache_creation_input_tokens", None
    )
    cache_read_input_tokens = getattr(usage, "cache_read_input_tokens", None)

    if (
        input_tokens is None
        and cache_creation_input_tokens is None
        and cache_read_input_tokens is None
    ):
        return None

    return (
        (input_tokens or 0)
        + (cache_creation_input_tokens or 0)
        + (cache_read_input_tokens or 0)
    )


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

    def extract_into(self, invocation: LLMInvocation) -> None:
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
        stream: "Stream[RawMessageStreamEvent] | MessageStream[ResponseFormatT]",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self._message: "Message | ParsedMessage[ResponseFormatT] | None" = None
        self._capture_content = capture_content
        self._finalized = False
        self._stream_input_tokens: int | None = None
        self._stream_output_tokens: int | None = None
        self._stream_cache_creation_input_tokens: int | None = None
        self._stream_cache_read_input_tokens: int | None = None

    def __enter__(self) -> "MessagesStreamWrapper[ResponseFormatT]":
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

    def __iter__(self) -> "MessagesStreamWrapper[ResponseFormatT]":
        return self

    def __next__(
        self,
    ) -> "RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]":
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
    def response(self):
        return _ResponseProxy(self.stream.response, self._stop)

    def _stop(self) -> None:
        if self._finalized:
            return
        with self._safe_instrumentation("response attribute extraction"):
            _set_response_attributes(
                self.invocation, self._message, self._capture_content
            )
            self._apply_stream_usage_attributes()
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

    def _record_usage(self, usage: object | None) -> None:
        if usage is None:
            return

        input_tokens = _get_usage_input_tokens(usage)
        output_tokens = getattr(usage, "output_tokens", None)
        cache_creation_input_tokens = getattr(
            usage, "cache_creation_input_tokens", None
        )
        cache_read_input_tokens = getattr(
            usage, "cache_read_input_tokens", None
        )

        if input_tokens is not None:
            self._stream_input_tokens = input_tokens
        if output_tokens is not None:
            self._stream_output_tokens = output_tokens
        if cache_creation_input_tokens is not None:
            self._stream_cache_creation_input_tokens = (
                cache_creation_input_tokens
            )
        if cache_read_input_tokens is not None:
            self._stream_cache_read_input_tokens = cache_read_input_tokens

    def _record_usage_from_chunk(
        self,
        chunk: "RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]",
    ) -> None:
        self._record_usage(getattr(chunk, "usage", None))
        message = getattr(chunk, "message", None)
        self._record_usage(getattr(message, "usage", None))

    def _apply_stream_usage_attributes(self) -> None:
        if self._stream_input_tokens is not None:
            self.invocation.input_tokens = self._stream_input_tokens
        if self._stream_output_tokens is not None:
            self.invocation.output_tokens = self._stream_output_tokens
        if self._stream_cache_creation_input_tokens is not None:
            self.invocation.attributes[
                GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS
            ] = self._stream_cache_creation_input_tokens
        if self._stream_cache_read_input_tokens is not None:
            self.invocation.attributes[
                GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS
            ] = self._stream_cache_read_input_tokens

    def _process_chunk(
        self,
        chunk: "RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]",
    ) -> None:
        """Accumulate a final message snapshot from a streaming chunk."""
        self._record_usage_from_chunk(chunk)
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
        stream: "AsyncStream[RawMessageStreamEvent] | AsyncMessageStream[ResponseFormatT]",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self._message: "Message | ParsedMessage[ResponseFormatT] | None" = None
        self._capture_content = capture_content
        self._finalized = False
        self._stream_input_tokens: int | None = None
        self._stream_output_tokens: int | None = None
        self._stream_cache_creation_input_tokens: int | None = None
        self._stream_cache_read_input_tokens: int | None = None

    async def __aenter__(
        self,
    ) -> "AsyncMessagesStreamWrapper[ResponseFormatT]":
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

    def __aiter__(self) -> "AsyncMessagesStreamWrapper[ResponseFormatT]":
        return self

    @property
    def response(self) -> Any:
        return _AsyncResponseProxy(self.stream.response, self._stop)

    async def __anext__(
        self,
    ) -> "RawMessageStreamEvent | ParsedMessageStreamEvent[ResponseFormatT]":
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


class MessagesStreamManagerWrapper(Generic[ResponseFormatT]):
    """Wrapper for sync Anthropic stream managers."""

    def __init__(
        self,
        manager: "MessageStreamManager[ResponseFormatT]",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: MessagesStreamWrapper[ResponseFormatT] | None = (
            None
        )

    def __enter__(self) -> MessagesStreamWrapper[ResponseFormatT]:
        stream = self._manager.__enter__()
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


class AsyncMessagesStreamManagerWrapper(Generic[ResponseFormatT]):
    """Wrapper for AsyncMessageStreamManager that handles telemetry.

    Wraps AsyncMessageStreamManager from the Anthropic SDK:
    https://github.com/anthropics/anthropic-sdk-python/blob/05220bc1c1079fe01f5c4babc007ec7a990859d9/src/anthropic/lib/streaming/_messages.py#L294
    """

    def __init__(
        self,
        manager: "AsyncMessageStreamManager[ResponseFormatT]",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: (
            AsyncMessagesStreamWrapper[ResponseFormatT] | None
        ) = None

    async def __aenter__(
        self,
    ) -> AsyncMessagesStreamWrapper[ResponseFormatT]:
        msg_stream = await self._manager.__aenter__()
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
