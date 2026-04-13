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

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    LLMInvocation,
    OutputMessage,
    Text,
)

from .utils import (
    COHERE_PROVIDER_NAME,
    create_chat_invocation,
    map_finish_reason,
    set_response_attributes,
)


def chat_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap ``V2Client.chat`` to emit GenAI telemetry."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_chat_invocation(kwargs, instance, capture_content=capture_content)
        )
        try:
            result = wrapped(*args, **kwargs)
            set_response_attributes(invocation, result, capture_content)
            handler.stop_llm(invocation)
            return result
        except Exception as error:
            handler.fail_llm(
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def async_chat_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap ``AsyncV2Client.chat`` to emit GenAI telemetry."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    async def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_chat_invocation(kwargs, instance, capture_content=capture_content)
        )
        try:
            result = await wrapped(*args, **kwargs)
            set_response_attributes(invocation, result, capture_content)
            handler.stop_llm(invocation)
            return result
        except Exception as error:
            handler.fail_llm(
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def chat_stream_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap ``V2Client.chat_stream`` to emit GenAI telemetry."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_chat_invocation(kwargs, instance, capture_content=capture_content)
        )
        try:
            result = wrapped(*args, **kwargs)
            return CohereStreamWrapper(result, handler, invocation, capture_content)
        except Exception as error:
            handler.fail_llm(
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def async_chat_stream_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap ``AsyncV2Client.chat_stream`` to emit GenAI telemetry."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    async def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_chat_invocation(kwargs, instance, capture_content=capture_content)
        )
        try:
            result = wrapped(*args, **kwargs)
            return AsyncCohereStreamWrapper(result, handler, invocation, capture_content)
        except Exception as error:
            handler.fail_llm(
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


class CohereStreamWrapper:
    """Wraps a synchronous Cohere chat_stream iterator to capture telemetry."""

    def __init__(
        self,
        stream,
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._stream = stream
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._content_parts: list[str] = []
        self._finish_reason = None
        self._response_id = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self._stream)
            self._process_event(event)
            return event
        except StopIteration:
            self._finalize()
            raise
        except Exception as error:
            self._handler.fail_llm(
                self._invocation,
                Error(type=type(error), message=str(error)),
            )
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._handler.fail_llm(
                self._invocation,
                Error(type=exc_type, message=str(exc_val)),
            )
        return False

    def _process_event(self, event):
        event_type = getattr(event, "type", None)

        if event_type == "message-start":
            delta = getattr(event, "delta", None)
            if delta:
                msg = getattr(delta, "message", None)
                if msg:
                    role = getattr(msg, "role", None)
                    if role:
                        self._invocation.attributes["_cohere_role"] = role
            event_id = getattr(event, "id", None)
            if event_id:
                self._response_id = event_id

        elif event_type == "content-delta":
            delta = getattr(event, "delta", None)
            if delta:
                msg = getattr(delta, "message", None)
                if msg:
                    content = getattr(msg, "content", None)
                    if content:
                        text = getattr(content, "text", None)
                        if text:
                            self._content_parts.append(text)

        elif event_type == "message-end":
            delta = getattr(event, "delta", None)
            if delta:
                self._finish_reason = getattr(delta, "finish_reason", None)
                usage = getattr(delta, "usage", None)
                if usage:
                    from .utils import _set_usage

                    _set_usage(self._invocation, usage)
            event_id = getattr(event, "id", None)
            if event_id:
                self._response_id = event_id

    def _finalize(self):
        if self._response_id:
            self._invocation.response_id = self._response_id

        if self._finish_reason is not None:
            self._invocation.finish_reasons = [
                map_finish_reason(self._finish_reason)
            ]

        if self._capture_content and self._content_parts:
            role = self._invocation.attributes.pop("_cohere_role", "assistant")
            full_text = "".join(self._content_parts)
            self._invocation.output_messages = [
                OutputMessage(
                    role=role,
                    parts=[Text(content=full_text)],
                    finish_reason=map_finish_reason(self._finish_reason),
                )
            ]
        else:
            self._invocation.attributes.pop("_cohere_role", None)

        self._handler.stop_llm(self._invocation)


class AsyncCohereStreamWrapper:
    """Wraps an async Cohere chat_stream iterator to capture telemetry."""

    def __init__(
        self,
        stream,
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._stream = stream
        self._handler = handler
        self._invocation = invocation
        self._capture_content = capture_content
        self._content_parts: list[str] = []
        self._finish_reason = None
        self._response_id = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = await self._stream.__anext__()
            self._process_event(event)
            return event
        except StopAsyncIteration:
            self._finalize()
            raise
        except Exception as error:
            self._handler.fail_llm(
                self._invocation,
                Error(type=type(error), message=str(error)),
            )
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._handler.fail_llm(
                self._invocation,
                Error(type=exc_type, message=str(exc_val)),
            )
        return False

    def _process_event(self, event):
        event_type = getattr(event, "type", None)

        if event_type == "message-start":
            delta = getattr(event, "delta", None)
            if delta:
                msg = getattr(delta, "message", None)
                if msg:
                    role = getattr(msg, "role", None)
                    if role:
                        self._invocation.attributes["_cohere_role"] = role
            event_id = getattr(event, "id", None)
            if event_id:
                self._response_id = event_id

        elif event_type == "content-delta":
            delta = getattr(event, "delta", None)
            if delta:
                msg = getattr(delta, "message", None)
                if msg:
                    content = getattr(msg, "content", None)
                    if content:
                        text = getattr(content, "text", None)
                        if text:
                            self._content_parts.append(text)

        elif event_type == "message-end":
            delta = getattr(event, "delta", None)
            if delta:
                self._finish_reason = getattr(delta, "finish_reason", None)
                usage = getattr(delta, "usage", None)
                if usage:
                    from .utils import _set_usage

                    _set_usage(self._invocation, usage)
            event_id = getattr(event, "id", None)
            if event_id:
                self._response_id = event_id

    def _finalize(self):
        if self._response_id:
            self._invocation.response_id = self._response_id

        if self._finish_reason is not None:
            self._invocation.finish_reasons = [
                map_finish_reason(self._finish_reason)
            ]

        if self._capture_content and self._content_parts:
            role = self._invocation.attributes.pop("_cohere_role", "assistant")
            full_text = "".join(self._content_parts)
            self._invocation.output_messages = [
                OutputMessage(
                    role=role,
                    parts=[Text(content=full_text)],
                    finish_reason=map_finish_reason(self._finish_reason),
                )
            ]
        else:
            self._invocation.attributes.pop("_cohere_role", None)

        self._handler.stop_llm(self._invocation)
