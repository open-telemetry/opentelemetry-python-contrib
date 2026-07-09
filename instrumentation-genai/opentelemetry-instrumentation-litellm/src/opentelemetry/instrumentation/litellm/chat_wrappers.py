# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from types import TracebackType
from typing import Any, Literal, Optional

from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)
from opentelemetry.util.genai.types import (
    OutputMessage,
    Text,
    ToolCallRequest,
)

from .chat_buffers import ChoiceBuffer
from .utils import (
    get_property_value,
    map_finish_reason,
    resolve_provider_from_response,
)


class _ChatStreamMixin:
    """Chat-specific hooks shared by sync and async stream wrappers.

    LiteLLM streams yield OpenAI-style ``ModelResponseStream`` chunks. Usage is
    only present on the final chunk when the caller passes
    ``stream_options={"include_usage": True}``.
    """

    _self_invocation: InferenceInvocation
    _self_capture_content: bool
    _self_choice_buffers: list[ChoiceBuffer]
    _self_response_id: Optional[str]
    _self_response_model: Optional[str]
    _self_provider: Optional[str]
    _self_prompt_tokens: Optional[int]
    _self_completion_tokens: Optional[int]

    def _set_response_model(self, chunk: Any) -> None:
        if self._self_response_model:
            return
        model = get_property_value(chunk, "model")
        if model:
            self._self_response_model = model

    def _set_response_id(self, chunk: Any) -> None:
        if self._self_response_id:
            return
        chunk_id = get_property_value(chunk, "id")
        if chunk_id:
            self._self_response_id = chunk_id

    def _set_provider(self, chunk: Any) -> None:
        if self._self_provider:
            return
        provider = resolve_provider_from_response(chunk)
        if provider:
            self._self_provider = provider

    def _build_streaming_response(self, chunk: Any) -> None:
        choices = get_property_value(chunk, "choices")
        if not choices:
            return

        for choice in choices:
            delta = get_property_value(choice, "delta")
            if not delta:
                continue

            index = get_property_value(choice, "index") or 0
            for idx in range(len(self._self_choice_buffers), index + 1):
                self._self_choice_buffers.append(ChoiceBuffer(idx))

            finish_reason = get_property_value(choice, "finish_reason")
            if finish_reason:
                self._self_choice_buffers[index].finish_reason = finish_reason

            content = get_property_value(delta, "content")
            if content is not None:
                self._self_choice_buffers[index].append_text_content(content)

            tool_calls = get_property_value(delta, "tool_calls")
            if tool_calls is not None:
                for tool_call in tool_calls:
                    self._self_choice_buffers[index].append_tool_call(
                        tool_call
                    )

    def _set_usage(self, chunk: Any) -> None:
        usage = get_property_value(chunk, "usage")
        if usage:
            self._self_prompt_tokens = get_property_value(
                usage, "prompt_tokens"
            )
            self._self_completion_tokens = get_property_value(
                usage, "completion_tokens"
            )

    def _process_chunk(self, chunk: Any) -> None:
        self._set_response_id(chunk)
        self._set_response_model(chunk)
        self._set_provider(chunk)
        self._build_streaming_response(chunk)
        self._set_usage(chunk)

    def _set_output_messages(self) -> None:
        if not self._self_capture_content:  # optimization
            return
        output_messages: list[OutputMessage] = []
        for choice in self._self_choice_buffers:
            message = OutputMessage(
                role="assistant",
                finish_reason=map_finish_reason(choice.finish_reason),
                parts=[],
            )
            if choice.text_content:
                message.parts.append(
                    Text(content="".join(choice.text_content))
                )
            if choice.tool_calls_buffers:
                tool_calls: list[ToolCallRequest] = []
                for tool_call in filter(None, choice.tool_calls_buffers):
                    arguments: Any = None
                    arguments_str = "".join(tool_call.arguments)
                    if arguments_str:
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = arguments_str
                    tool_calls.append(
                        ToolCallRequest(
                            name=tool_call.function_name,
                            id=tool_call.tool_call_id,
                            arguments=arguments,
                        )
                    )
                message.parts.extend(tool_calls)
            output_messages.append(message)

        self._self_invocation.output_messages = output_messages

    def _on_stream_end(self) -> None:
        self._cleanup()

    def _on_stream_error(self, error: BaseException) -> None:
        self._cleanup(error)

    def _cleanup(self, error: Optional[BaseException] = None) -> None:
        if self._self_provider:
            self._self_invocation.provider = self._self_provider
        self._self_invocation.response_model_name = self._self_response_model
        self._self_invocation.response_id = self._self_response_id
        self._self_invocation.input_tokens = self._self_prompt_tokens
        self._self_invocation.output_tokens = self._self_completion_tokens
        finish_reasons = [
            map_finish_reason(choice.finish_reason)
            for choice in self._self_choice_buffers
            if choice.finish_reason
        ]
        if finish_reasons:
            self._self_invocation.finish_reasons = finish_reasons

        self._set_output_messages()

        if error:
            self._self_invocation.fail(error)
        else:
            self._self_invocation.stop()


class ChatStreamWrapper(_ChatStreamMixin, SyncStreamWrapper[Any]):
    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_choice_buffers = []
        self._self_capture_content = capture_content
        self._self_response_id = None
        self._self_response_model = None
        self._self_provider = None
        self._self_prompt_tokens = None
        self._self_completion_tokens = None

    def close(self) -> None:
        # litellm's sync ``CustomStreamWrapper`` does not expose ``close()``,
        # so finalize telemetry directly rather than delegating to the wrapped
        # stream (which the shared base would attempt).
        self._safe_finalize_success()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_val is not None:
            self._safe_finalize_failure(exc_val)
        else:
            self._safe_finalize_success()
        return False


class AsyncChatStreamWrapper(_ChatStreamMixin, AsyncStreamWrapper[Any]):
    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_choice_buffers = []
        self._self_capture_content = capture_content
        self._self_response_id = None
        self._self_response_model = None
        self._self_provider = None
        self._self_prompt_tokens = None
        self._self_completion_tokens = None

    async def close(self) -> None:
        # litellm's async ``CustomStreamWrapper`` exposes ``aclose()`` rather
        # than ``close()``; finalize telemetry then best-effort close the
        # wrapped stream.
        aclose = getattr(self.__wrapped__, "aclose", None)
        if callable(aclose):
            await aclose()
        self._safe_finalize_success()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_val is not None:
            self._safe_finalize_failure(exc_val)
        else:
            self._safe_finalize_success()
        return False


__all__ = [
    "AsyncChatStreamWrapper",
    "ChatStreamWrapper",
]
