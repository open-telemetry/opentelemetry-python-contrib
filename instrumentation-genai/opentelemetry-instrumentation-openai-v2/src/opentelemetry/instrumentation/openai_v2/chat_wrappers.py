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

import json
from typing import Any, Optional

from openai import AsyncStream, Stream

from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.util.genai._stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import (
    OutputMessage,
    Text,
    ToolCallRequest,
)

from .chat_buffers import ChoiceBuffer


class _ChatStreamMixin:
    """Chat-specific hooks shared by sync and async stream wrappers."""

    invocation: InferenceInvocation
    capture_content: bool
    choice_buffers: list
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    service_tier: Optional[str] = None
    finish_reasons: list = []
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    def _set_response_model(self, chunk):
        if self.response_model:
            return

        if getattr(chunk, "model", None):
            self.response_model = chunk.model

    def _set_response_id(self, chunk):
        if self.response_id:
            return

        if getattr(chunk, "id", None):
            self.response_id = chunk.id

    def _set_response_service_tier(self, chunk):
        if self.service_tier:
            return

        if getattr(chunk, "service_tier", None):
            self.service_tier = chunk.service_tier

    def _build_streaming_response(self, chunk):
        if getattr(chunk, "choices", None) is None:
            return

        choices = chunk.choices
        for choice in choices:
            if not choice.delta:
                continue

            for idx in range(len(self.choice_buffers), choice.index + 1):
                self.choice_buffers.append(ChoiceBuffer(idx))

            if choice.finish_reason:
                self.choice_buffers[
                    choice.index
                ].finish_reason = choice.finish_reason

            if choice.delta.content is not None:
                self.choice_buffers[choice.index].append_text_content(
                    choice.delta.content
                )

            if choice.delta.tool_calls is not None:
                for tool_call in choice.delta.tool_calls:
                    self.choice_buffers[choice.index].append_tool_call(
                        tool_call
                    )

    def _set_usage(self, chunk):
        if getattr(chunk, "usage", None):
            self.completion_tokens = chunk.usage.completion_tokens
            self.prompt_tokens = chunk.usage.prompt_tokens

    def _process_chunk(self, chunk):
        self._set_response_id(chunk)
        self._set_response_model(chunk)
        self._set_response_service_tier(chunk)
        self._build_streaming_response(chunk)
        self._set_usage(chunk)

    def _set_output_messages(self):
        if not self.capture_content:  # optimization
            return
        output_messages = []
        for choice in self.choice_buffers:
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
                for tool_call in choice.tool_calls_buffers:
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

        self.invocation.output_messages = output_messages

    def _stop_stream(self) -> None:
        self._cleanup()

    def _fail_stream(self, error: BaseException) -> None:
        self._cleanup(error)

    def parse(self):
        """Called when using with_raw_response with stream=True."""
        return self

    def _cleanup(self, error: Optional[BaseException] = None) -> None:
        self.invocation.response_model_name = self.response_model
        self.invocation.response_id = self.response_id
        self.invocation.input_tokens = self.prompt_tokens
        self.invocation.output_tokens = self.completion_tokens
        # TODO: Derive finish_reasons from choice_buffers so streaming
        # invocations match non-streaming response finalization.
        self.invocation.finish_reasons = self.finish_reasons
        if self.service_tier:
            self.invocation.attributes.update(
                {
                    OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: self.service_tier
                },
            )

        self._set_output_messages()

        if error:
            self.invocation.fail(error)
        else:
            self.invocation.stop()


class ChatStreamWrapper(
    _ChatStreamMixin,
    SyncStreamWrapper[Any],
):
    def __init__(
        self,
        stream: Stream,
        invocation: InferenceInvocation,
        capture_content: bool,
    ):
        super().__init__(stream)
        self.invocation = invocation
        self.choice_buffers = []
        self.capture_content = capture_content


class AsyncChatStreamWrapper(
    _ChatStreamMixin,
    AsyncStreamWrapper[Any],
):

    def __init__(
        self,
        stream: AsyncStream,
        invocation: InferenceInvocation,
        capture_content: bool,
    ):
        super().__init__(stream)
        self.invocation = invocation
        self.choice_buffers = []
        self.capture_content = capture_content


__all__ = [
    "AsyncChatStreamWrapper",
    "ChatStreamWrapper",
]
