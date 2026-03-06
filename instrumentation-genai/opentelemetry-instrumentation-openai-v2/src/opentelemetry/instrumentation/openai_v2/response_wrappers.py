"""Wrappers for OpenAI Responses API streams and stream managers."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Generator, Generic, TypeVar

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation

# OpenAI Responses internals are version-gated (added in openai>=1.66.0), so
# pylint may not resolve them in all lint environments even though we guard
# runtime usage with ImportError fallbacks below.
try:
    from openai.lib.streaming.responses._events import (  # pylint: disable=no-name-in-module
        ResponseCompletedEvent,
    )
    from openai.types.responses import (  # pylint: disable=no-name-in-module
        ResponseCreatedEvent,
        ResponseErrorEvent,
        ResponseFailedEvent,
        ResponseIncompleteEvent,
        ResponseInProgressEvent,
    )

    _RESPONSE_EVENTS_WITH_RESPONSE = (
        ResponseCreatedEvent,
        ResponseInProgressEvent,
        ResponseFailedEvent,
        ResponseIncompleteEvent,
        ResponseCompletedEvent,
    )
except ImportError:
    ResponseCompletedEvent = None
    ResponseCreatedEvent = None
    ResponseErrorEvent = None
    ResponseFailedEvent = None
    ResponseIncompleteEvent = None
    ResponseInProgressEvent = None
    _RESPONSE_EVENTS_WITH_RESPONSE = ()

try:
    from opentelemetry.instrumentation.openai_v2.response_extractors import (  # pylint: disable=no-name-in-module
        _set_invocation_response_attributes,
    )
except ImportError:
    _set_invocation_response_attributes = None

if TYPE_CHECKING:
    from openai.lib.streaming.responses._events import (  # pylint: disable=no-name-in-module
        ResponseStreamEvent,
    )
    from openai.lib.streaming.responses._responses import (
        ResponseStream,
        ResponseStreamManager,
    )  # pylint: disable=no-name-in-module
    from openai.types.responses import (  # pylint: disable=no-name-in-module
        ParsedResponse,
        Response,
    )

_logger = logging.getLogger(__name__)
TextFormatT = TypeVar("TextFormatT")
ResponseT = TypeVar("ResponseT")


def _set_response_attributes(
    invocation: "LLMInvocation",
    result: "ParsedResponse[TextFormatT] | Response | None",
    capture_content: bool,
) -> None:
    if _set_invocation_response_attributes is None:
        return
    _set_invocation_response_attributes(invocation, result, capture_content)


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


class ResponseStreamWrapper(Generic[TextFormatT]):
    """Wrapper for OpenAI Responses API stream objects.

    Wraps ResponseStream from the OpenAI SDK:
    https://github.com/openai/openai-python/blob/656e3cab4a18262a49b961d41293367e45ee71b9/src/openai/_streaming.py#L55
    """

    def __init__(
        self,
        stream: "ResponseStream[TextFormatT]",
        handler: TelemetryHandler,
        invocation: "LLMInvocation",
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
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
        return self

    # TODO: Migrate passthrough delegation to wrapt.ObjectProxy once wrapt 2
    # typing support is available (wrapt PR #3903).
    def __getattr__(self, name: str):
        return getattr(self.stream, name)

    @property
    def response(self):
        response = self.stream.response
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
        response: "ParsedResponse[TextFormatT] | Response | None" = None

        if isinstance(event, _RESPONSE_EVENTS_WITH_RESPONSE):
            response = event.response

        if response and not self.invocation.request_model:
            model = response.model
            if model:
                self.invocation.request_model = model

        if isinstance(event, ResponseCompletedEvent):
            self._stop(response)
            return

        if isinstance(event, (ResponseFailedEvent, ResponseIncompleteEvent)):
            with self._safe_instrumentation("response attribute extraction"):
                _set_response_attributes(
                    self.invocation, response, self._capture_content
                )
            self._fail(event_type, RuntimeError)
            return

        if isinstance(event, ResponseErrorEvent):
            error_type = event.code or "response.error"
            message = event.message or error_type
            self._fail(message, RuntimeError)


class ResponseStreamManagerWrapper(Generic[TextFormatT]):
    """Wrapper for OpenAI Responses API stream managers.

    Wraps ResponseStreamManager from the OpenAI SDK:
    https://github.com/openai/openai-python/blob/656e3cab4a18262a49b961d41293367e45ee71b9/src/openai/lib/streaming/responses/_responses.py#L95
    """

    def __init__(
        self,
        manager: "ResponseStreamManager[TextFormatT]",
        handler: TelemetryHandler,
        invocation: "LLMInvocation",
        capture_content: bool,
    ):
        self._manager = manager
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._stream_wrapper: ResponseStreamWrapper[TextFormatT] | None = None

    def __enter__(self) -> ResponseStreamWrapper[TextFormatT]:
        stream = self._manager.__enter__()
        self._stream_wrapper = ResponseStreamWrapper(
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
    ) -> bool:
        suppressed = False
        try:
            suppressed = self._manager.__exit__(exc_type, exc_val, exc_tb)
            return suppressed
        finally:
            if self._stream_wrapper is not None:
                if suppressed:
                    self._stream_wrapper.__exit__(None, None, None)
                else:
                    self._stream_wrapper.__exit__(exc_type, exc_val, exc_tb)
                self._stream_wrapper = None

    # TODO: Migrate passthrough delegation to wrapt.ObjectProxy once wrapt 2
    # typing support is available (wrapt PR #3903).
    def __getattr__(self, name: str):
        return getattr(self._manager, name)
