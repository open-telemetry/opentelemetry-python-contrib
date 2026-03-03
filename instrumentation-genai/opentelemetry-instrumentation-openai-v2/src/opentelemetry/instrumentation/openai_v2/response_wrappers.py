"""Wrappers for OpenAI Responses API streams and stream managers."""

from __future__ import annotations

import logging
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

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

    from opentelemetry.util.genai.handler import TelemetryHandler
    from opentelemetry.util.genai.types import (  # pylint: disable=no-name-in-module
        LLMInvocation,
    )


_logger = logging.getLogger(__name__)
TextFormatT = TypeVar("TextFormatT")
ResponseT = TypeVar("ResponseT")


def _set_response_attributes(
    invocation: "LLMInvocation",
    result: "ParsedResponse[TextFormatT] | Response | None",
    capture_content: bool,
) -> None:
    from .response_extractors import (  # pylint: disable=import-outside-toplevel
        _set_invocation_response_attributes,
    )

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
    """Wrapper for OpenAI Responses API stream objects."""

    def __init__(
        self,
        stream: "ResponseStream[TextFormatT]",
        handler: "TelemetryHandler",
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
        self._safe_instrumentation(
            lambda: self.process_event(event),
            "event processing",
        )
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
        self._safe_instrumentation(
            lambda: _set_response_attributes(
                self.invocation, result, self._capture_content
            ),
            "response attribute extraction",
        )
        self._safe_instrumentation(
            lambda: self.handler.stop_llm(self.invocation),
            "stop_llm",
        )
        self._finalized = True

    def _fail(self, message: str, error_type: type[BaseException]) -> None:
        from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel,no-name-in-module
            Error,
        )

        if self._finalized:
            return
        self._safe_instrumentation(
            lambda: self.handler.fail_llm(
                self.invocation, Error(message=message, type=error_type)
            ),
            "fail_llm",
        )
        self._finalized = True

    @staticmethod
    def _safe_instrumentation(
        callback: Callable[[], None], context: str
    ) -> None:
        try:
            callback()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "OpenAI responses instrumentation error during %s",
                context,
                exc_info=True,
            )

    def process_event(self, event: "ResponseStreamEvent[TextFormatT]") -> None:
        from openai.lib.streaming.responses._events import (  # pylint: disable=import-outside-toplevel,no-name-in-module
            ResponseCompletedEvent,
        )
        from openai.types.responses import (  # pylint: disable=import-outside-toplevel,no-name-in-module
            ResponseCreatedEvent,
            ResponseErrorEvent,
            ResponseFailedEvent,
            ResponseInProgressEvent,
            ResponseIncompleteEvent,
        )

        event_type = event.type
        response: "ParsedResponse[TextFormatT] | Response | None" = None

        if isinstance(
            event,
            (
                ResponseCreatedEvent,
                ResponseInProgressEvent,
                ResponseFailedEvent,
                ResponseIncompleteEvent,
                ResponseCompletedEvent,
            ),
        ):
            response = event.response

        if response and not self.invocation.request_model:
            model = response.model
            if model:
                self.invocation.request_model = model

        if isinstance(event, ResponseCompletedEvent):
            self._stop(response)
            return

        if isinstance(event, (ResponseFailedEvent, ResponseIncompleteEvent)):
            self._safe_instrumentation(
                lambda: _set_response_attributes(
                    self.invocation, response, self._capture_content
                ),
                "response attribute extraction",
            )
            self._fail(event_type, RuntimeError)
            return

        if isinstance(event, ResponseErrorEvent):
            error_type = event.code or "response.error"
            message = event.message or error_type
            self._fail(message, RuntimeError)


class ResponseStreamManagerWrapper(Generic[TextFormatT]):
    """Wrapper for OpenAI Responses API stream managers."""

    def __init__(
        self,
        manager: "ResponseStreamManager[TextFormatT]",
        handler: "TelemetryHandler",
        invocation: "LLMInvocation",
        capture_content: bool,
    ):
        self._manager = manager
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content

    def __enter__(self) -> ResponseStreamWrapper[TextFormatT]:
        stream = self._manager.__enter__()
        return ResponseStreamWrapper(
            stream,
            self._handler,
            self._invocation,
            self._capture_content,
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return self._manager.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str):
        return getattr(self._manager, name)
