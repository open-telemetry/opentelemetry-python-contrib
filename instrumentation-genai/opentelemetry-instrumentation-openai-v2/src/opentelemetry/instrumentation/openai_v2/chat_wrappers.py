# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Optional

from openai import AsyncStream, Stream
from openai.types.chat import ChatCompletionChunk

from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
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


class _ChatStreamMixin:
    """Chat-specific hooks shared by sync and async stream wrappers."""

    _self_invocation: InferenceInvocation
    _self_capture_content: bool
    _self_choice_buffers: list[ChoiceBuffer]
    _self_response_id: Optional[str]
    _self_response_model: Optional[str]
    _self_service_tier: Optional[str]
    _self_prompt_tokens: Optional[int]
    _self_completion_tokens: Optional[int]

    def _set_response_model(self, chunk: ChatCompletionChunk) -> None:
        if self._self_response_model:
            return

        if chunk.model:
            self._self_response_model = chunk.model

    def _set_response_id(self, chunk: ChatCompletionChunk) -> None:
        if self._self_response_id:
            return

        if chunk.id:
            self._self_response_id = chunk.id

    def _set_response_service_tier(self, chunk: ChatCompletionChunk) -> None:
        if self._self_service_tier:
            return

        service_tier = getattr(chunk, "service_tier", None)
        if service_tier:
            self._self_service_tier = service_tier

    def _build_streaming_response(self, chunk: ChatCompletionChunk) -> None:
        if chunk.choices is None:
            return

        for choice in chunk.choices:
            if not choice.delta:
                continue

            for idx in range(len(self._self_choice_buffers), choice.index + 1):
                self._self_choice_buffers.append(ChoiceBuffer(idx))

            if choice.finish_reason:
                self._self_choice_buffers[
                    choice.index
                ].finish_reason = choice.finish_reason

            if choice.delta.content is not None:
                self._self_choice_buffers[choice.index].append_text_content(
                    choice.delta.content
                )

            if choice.delta.tool_calls is not None:
                for tool_call in choice.delta.tool_calls:
                    self._self_choice_buffers[choice.index].append_tool_call(
                        tool_call
                    )

    def _set_usage(self, chunk: ChatCompletionChunk) -> None:
        usage = getattr(chunk, "usage", None)
        if usage:
            self._self_completion_tokens = usage.completion_tokens
            self._self_prompt_tokens = usage.prompt_tokens

    def _process_chunk(self, chunk: ChatCompletionChunk) -> None:
        self._set_response_id(chunk)
        self._set_response_model(chunk)
        self._set_response_service_tier(chunk)
        self._build_streaming_response(chunk)
        self._set_usage(chunk)

    def _set_output_messages(self) -> None:
        if not self._self_capture_content:  # optimization
            return
        output_messages = []
        for choice in self._self_choice_buffers:
            message = OutputMessage(
                role="assistant",
                finish_reason=choice.finish_reason or "error",
                parts=[],
            )
            if choice.text_content:
                message.parts.append(
                    Text(content="".join(choice.text_content))
                )
            if choice.tool_calls_buffers:
                tool_calls = []
                for tool_call in filter(None, choice.tool_calls_buffers):
                    arguments = None
                    arguments_str = "".join(tool_call.arguments)
                    if arguments_str:
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = arguments_str
                    tool_call_part = ToolCallRequest(
                        name=tool_call.function_name,
                        id=tool_call.tool_call_id,
                        arguments=arguments,
                    )
                    tool_calls.append(tool_call_part)
                message.parts.extend(tool_calls)
            output_messages.append(message)

        self._self_invocation.output_messages = output_messages

    def _on_stream_end(self) -> None:
        self._cleanup()

    def _on_stream_error(self, error: BaseException) -> None:
        self._cleanup(error)

    def parse(self) -> _ChatStreamMixin:
        """Called when using with_raw_response with stream=True."""
        return self

    def _cleanup(self, error: Optional[BaseException] = None) -> None:
        self._self_invocation.response_model_name = self._self_response_model
        self._self_invocation.response_id = self._self_response_id
        self._self_invocation.input_tokens = self._self_prompt_tokens
        self._self_invocation.output_tokens = self._self_completion_tokens
        finish_reasons = [
            choice.finish_reason
            for choice in self._self_choice_buffers
            if choice.finish_reason
        ]
        if finish_reasons:
            self._self_invocation.finish_reasons = finish_reasons
        if self._self_service_tier:
            self._self_invocation.attributes.update(
                {
                    OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: self._self_service_tier
                },
            )

        self._set_output_messages()

        if error:
            self._self_invocation.fail(error)
        else:
            self._self_invocation.stop()


class ChatStreamWrapper(
    _ChatStreamMixin,
    SyncStreamWrapper[ChatCompletionChunk],
):
    def __init__(
        self,
        stream: Stream[ChatCompletionChunk],
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_choice_buffers = []
        self._self_capture_content = capture_content
        self._self_response_id = None
        self._self_response_model = None
        self._self_service_tier = None
        self._self_prompt_tokens = None
        self._self_completion_tokens = None


class AsyncChatStreamWrapper(
    _ChatStreamMixin,
    AsyncStreamWrapper[ChatCompletionChunk],
):
    def __init__(
        self,
        stream: AsyncStream[ChatCompletionChunk],
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_choice_buffers = []
        self._self_capture_content = capture_content
        self._self_response_id = None
        self._self_response_model = None
        self._self_service_tier = None
        self._self_prompt_tokens = None
        self._self_completion_tokens = None


__all__ = [
    "AsyncChatStreamWrapper",
    "ChatStreamWrapper",
]
