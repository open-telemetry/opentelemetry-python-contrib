# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Wrappers for OpenAI Responses API streams and stream managers."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, ExitStack, contextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Generator, Generic, TypeVar

from opentelemetry.util.genai.types import Error

try:
    from opentelemetry.instrumentation.openai_v2.response_extractors import (  # pylint: disable=no-name-in-module
        set_invocation_response_attributes,
    )
except ImportError:
    set_invocation_response_attributes = None

if TYPE_CHECKING:
    from openai.lib.streaming.responses._events import (  # pylint: disable=no-name-in-module
        ResponseStreamEvent,
    )
    from openai.lib.streaming.responses._responses import (
        AsyncResponseStream,
        AsyncResponseStreamManager,
        ResponseStream,
        ResponseStreamManager,
    )  # pylint: disable=no-name-in-module
    from openai.types.responses import (  # pylint: disable=no-name-in-module
        ParsedResponse,
        Response,
    )

    from opentelemetry.util.genai._invocation import GenAIInvocation

_logger = logging.getLogger(__name__)
TextFormatT = TypeVar("TextFormatT")
ResponseT = TypeVar("ResponseT")


def _set_response_attributes(
    invocation: "GenAIInvocation",
    result: "ParsedResponse[TextFormatT] | Response | None",
    capture_content: bool,
) -> None:
    if set_invocation_response_attributes is None:
        return
    set_invocation_response_attributes(invocation, result, capture_content)


def _get_stream_response(stream):
    try:
        return stream._response
    except AttributeError:
        try:
            return stream.response
        except AttributeError:
            return None


class _ResponseProxy(Generic[ResponseT]):
    def __init__(self, response: ResponseT, finalize: Callable[[], None]):
        self._response = response
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
        self._response = response
        self._finalize = finalize

    async def aclose(self) -> None:
        try:
            await self._response.aclose()
        finally:
            self._finalize()

    def __getattr__(self, name: str):
        return getattr(self._response, name)


class ResponseStreamWrapper(Generic[TextFormatT]):
    """Wrapper for OpenAI Responses API stream objects.

    Wraps ResponseStream from the OpenAI SDK:
    https://github.com/openai/openai-python/blob/656e3cab4a18262a49b961d41293367e45ee71b9/src/openai/_streaming.py#L55
    """

    def __init__(
        self,
        stream: "ResponseStream[TextFormatT]",
        invocation: "GenAIInvocation",
        capture_content: bool,
    ):
        self.stream = stream
        self.invocation = invocation
        self._capture_content = capture_content
        self._finalized = False

    def __enter__(self) -> "ResponseStreamWrapper":
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
            self._stop(None)

    def __iter__(self) -> "ResponseStreamWrapper":
        return self

    def __next__(self) -> "ResponseStreamEvent[TextFormatT]":
        try:
            event = next(self.stream)
        except StopIteration:
            self._stop(None)
            raise
        except Exception as error:
            self._fail(str(error), type(error))
            raise
        with self._safe_instrumentation("event processing"):
            self.process_event(event)
        return event

    def get_final_response(self) -> "ParsedResponse[TextFormatT]":
        self.until_done()
        return self.stream.get_final_response()

    def until_done(self) -> "ResponseStreamWrapper":
        for _ in self:
            pass
        return self

    def parse(self) -> "ResponseStreamWrapper":
        """Called when using with_raw_response with stream=True."""
        return self

    # TODO: Replace __getattr__ passthrough with wrapt.ObjectProxy in a future
    # cleanup once wrapt 2 typing support is available (wrapt PR #3903).
    def __getattr__(self, name: str):
        return getattr(self.stream, name)

    @property
    def response(self):
        response = _get_stream_response(self.stream)
        if response is None:
            return None
        return _ResponseProxy(response, lambda: self._stop(None))

    def _stop(
        self, result: "ParsedResponse[TextFormatT] | Response | None"
    ) -> None:
        if self._finalized:
            return
        with self._safe_instrumentation("response attribute extraction"):
            _set_response_attributes(
                self.invocation, result, self._capture_content
            )
        with self._safe_instrumentation("inference.stop"):
            self.invocation.stop()
        self._finalized = True

    def _fail(self, message: str, error_type: type[BaseException]) -> None:
        if self._finalized:
            return
        with self._safe_instrumentation("inference.fail"):
            self.invocation.fail(Error(message=message, type=error_type))
        self._finalized = True

    @staticmethod
    @contextmanager
    def _safe_instrumentation(context: str) -> Generator[None, None, None]:
        try:
            yield
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "OpenAI responses instrumentation error during %s",
                context,
                exc_info=True,
                stacklevel=2,
            )

    def process_event(self, event: "ResponseStreamEvent[TextFormatT]") -> None:
        event_type = event.type
        response: "ParsedResponse[TextFormatT] | Response | None" = getattr(
            event, "response", None
        )

        if response and not self.invocation.request_model:
            model = response.model
            if model:
                self.invocation.request_model = model

        if event_type == "response.completed":
            self._stop(response)
            return

        if event_type in {"response.failed", "response.incomplete"}:
            with self._safe_instrumentation("response attribute extraction"):
                _set_response_attributes(
                    self.invocation, response, self._capture_content
                )
            self._fail(event_type, RuntimeError)
            return

        if event_type == "response.error":
            error_type = getattr(event, "code", None) or "response.error"
            message = getattr(event, "message", None) or error_type
            self._fail(message, RuntimeError)


class ResponseStreamManagerWrapper(Generic[TextFormatT]):
    """Wrapper for OpenAI Responses API stream managers.

    Wraps ResponseStreamManager from the OpenAI SDK:
    https://github.com/openai/openai-python/blob/656e3cab4a18262a49b961d41293367e45ee71b9/src/openai/lib/streaming/responses/_responses.py#L95
    """

    def __init__(
        self,
        manager: "ResponseStreamManager[TextFormatT]",
        invocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: ResponseStreamWrapper[TextFormatT] | None = None

    def __enter__(self) -> ResponseStreamWrapper[TextFormatT]:
        stream = self._manager.__enter__()
        self._stream_wrapper = ResponseStreamWrapper(
            stream,
            self._invocation,
            self._capture_content,
        )
        return self._stream_wrapper

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
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

    def parse(self) -> "ResponseStreamManagerWrapper[TextFormatT]":
        raise NotImplementedError(
            "ResponseStreamManagerWrapper.parse() is not implemented"
        )

    # TODO: Replace __getattr__ passthrough with wrapt.ObjectProxy in a future
    # cleanup once wrapt 2 typing support is available (wrapt PR #3903).
    def __getattr__(self, name: str):
        return getattr(self._manager, name)


class AsyncResponseStreamWrapper(ResponseStreamWrapper[TextFormatT]):
    """Wrapper for async OpenAI Responses API stream objects."""

    stream: "AsyncResponseStream[TextFormatT]"

    async def __aenter__(self) -> "AsyncResponseStreamWrapper[TextFormatT]":
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

    async def close(self) -> None:
        try:
            await self.stream.close()
        finally:
            self._stop(None)

    def __aiter__(self) -> "AsyncResponseStreamWrapper[TextFormatT]":
        return self

    async def __anext__(self) -> "ResponseStreamEvent[TextFormatT]":
        try:
            event = await self.stream.__anext__()
        except StopAsyncIteration:
            self._stop(None)
            raise
        except Exception as error:
            self._fail(str(error), type(error))
            raise
        with self._safe_instrumentation("event processing"):
            self.process_event(event)
        return event

    async def get_final_response(self) -> "ParsedResponse[TextFormatT]":
        await self.until_done()
        return await self.stream.get_final_response()

    async def until_done(self) -> "AsyncResponseStreamWrapper[TextFormatT]":
        async for _ in self:
            pass
        return self

    def parse(self) -> "AsyncResponseStreamWrapper[TextFormatT]":
        """Called when using with_raw_response with stream=True."""
        return self

    @property
    def response(self):
        response = _get_stream_response(self.stream)
        if response is None:
            return None
        return _AsyncResponseProxy(response, lambda: self._stop(None))


class AsyncResponseStreamManagerWrapper(Generic[TextFormatT]):
    """Wrapper for async OpenAI Responses API stream managers."""

    def __init__(
        self,
        manager: "AsyncResponseStreamManager[TextFormatT]",
        invocation,
        capture_content: bool,
    ):
        self._manager = manager
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: (
            AsyncResponseStreamWrapper[TextFormatT] | None
        ) = None

    async def __aenter__(self) -> AsyncResponseStreamWrapper[TextFormatT]:
        stream = await self._manager.__aenter__()
        self._stream_wrapper = AsyncResponseStreamWrapper(
            stream,
            self._invocation,
            self._capture_content,
        )
        return self._stream_wrapper

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
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

    def parse(self) -> "AsyncResponseStreamManagerWrapper[TextFormatT]":
        raise NotImplementedError(
            "AsyncResponseStreamManagerWrapper.parse() is not implemented"
        )

    # TODO: Replace __getattr__ passthrough with wrapt.ObjectProxy in a future
    # cleanup once wrapt 2 typing support is available (wrapt PR #3903).
    def __getattr__(self, name: str):
        return getattr(self._manager, name)
