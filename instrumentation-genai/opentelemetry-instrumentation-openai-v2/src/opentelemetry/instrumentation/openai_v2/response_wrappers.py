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

import logging
from typing import TYPE_CHECKING, Any, Callable

from opentelemetry.util.genai.types import Error

from .response_extractors import _set_invocation_response_attributes

if TYPE_CHECKING:
    from opentelemetry.util.genai.handler import TelemetryHandler
    from opentelemetry.util.genai.types import LLMInvocation


_logger = logging.getLogger(__name__)


class _ResponseProxy:
    def __init__(self, response, finalize):
        self._response = response
        self._finalize = finalize

    def close(self):
        try:
            self._response.close()
        finally:
            self._finalize(None)

    def __getattr__(self, name):
        return getattr(self._response, name)


class ResponseStreamWrapper:
    """Wrapper for OpenAI Responses API streams using TelemetryHandler."""

    def __init__(
        self,
        stream: Any,
        handler: "TelemetryHandler",
        invocation: "LLMInvocation",
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self._capture_content = capture_content
        self._finalized = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._fail(
                    str(exc_val), type(exc_val) if exc_val else Exception
                )
        finally:
            self.close()
        return False

    def close(self):
        try:
            if hasattr(self.stream, "close"):
                self.stream.close()
        finally:
            self._stop(None)

    def __iter__(self):
        return self

    def __next__(self):
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

    def get_final_response(self):
        if not hasattr(self.stream, "get_final_response"):
            raise AttributeError("get_final_response is not available")
        self.until_done()
        return self.stream.get_final_response()

    def until_done(self):
        for _ in self:
            pass
        return self

    def parse(self):
        """Called when using with_raw_response with stream=True."""
        return self

    def __getattr__(self, name):
        return getattr(self.stream, name)

    @property
    def response(self):
        response = getattr(self.stream, "response", None)
        if response is None:
            return None
        return _ResponseProxy(response, lambda *_: self._stop(None))

    def _stop(self, result: Any):
        if self._finalized:
            return
        self._safe_instrumentation(
            lambda: _set_invocation_response_attributes(
                self.invocation, result, self._capture_content
            ),
            "response attribute extraction",
        )
        self._safe_instrumentation(
            lambda: self.handler.stop_llm(self.invocation),
            "stop_llm",
        )
        self._finalized = True

    def _fail(self, message: str, error_type: type[BaseException]):
        if self._finalized:
            return
        self._safe_instrumentation(
            lambda: self.handler.fail_llm(
                self.invocation, Error(message=message, type=error_type)
            )
            if Error is not None
            else None,
            "fail_llm",
        )
        self._finalized = True

    @staticmethod
    def _safe_instrumentation(
        callback: Callable[[], object], context: str
    ) -> None:
        try:
            callback()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "OpenAI responses instrumentation error during %s",
                context,
                exc_info=True,
            )

    def process_event(self, event):
        event_type = getattr(event, "type", None)
        response = getattr(event, "response", None)

        if response and not self.invocation.request_model:
            model = getattr(response, "model", None)
            if model:
                self.invocation.request_model = model

        if event_type == "response.completed":
            self._stop(response)
            return

        if event_type in {"response.failed", "response.incomplete"}:
            _set_invocation_response_attributes(
                self.invocation, response, self._capture_content
            )
            self._fail(event_type, RuntimeError)
            return

        if event_type == "error":
            error_type = getattr(event, "code", None) or "response.error"
            message = getattr(event, "message", None) or error_type
            self._fail(message, RuntimeError)
            return
