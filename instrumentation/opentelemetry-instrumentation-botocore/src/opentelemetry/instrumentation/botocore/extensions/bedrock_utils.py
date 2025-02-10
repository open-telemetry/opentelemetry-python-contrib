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
from os import environ
from typing import Callable, Dict, Union

from botocore.eventstream import EventStream, EventStreamError
from wrapt import ObjectProxy

from opentelemetry._events import Event
from opentelemetry.instrumentation.botocore.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_SYSTEM,
    GenAiSystemValues,
)

_StreamDoneCallableT = Callable[[Dict[str, Union[int, str]]], None]
_StreamErrorCallableT = Callable[[Exception], None]


# pylint: disable=abstract-method
class ConverseStreamWrapper(ObjectProxy):
    """Wrapper for botocore.eventstream.EventStream"""

    def __init__(
        self,
        stream: EventStream,
        stream_done_callback: _StreamDoneCallableT,
        stream_error_callback: _StreamErrorCallableT,
    ):
        super().__init__(stream)

        self._stream_done_callback = stream_done_callback
        self._stream_error_callback = stream_error_callback
        # accumulating things in the same shape of non-streaming version
        # {"usage": {"inputTokens": 0, "outputTokens": 0}, "stopReason": "finish"}
        self._response = {}

    def __iter__(self):
        try:
            for event in self.__wrapped__:
                self._process_event(event)
                yield event
        except EventStreamError as exc:
            self._stream_error_callback(exc)
            raise

    def _process_event(self, event):
        if "messageStart" in event:
            # {'messageStart': {'role': 'assistant'}}
            return

        if "contentBlockDelta" in event:
            # {'contentBlockDelta': {'delta': {'text': "Hello"}, 'contentBlockIndex': 0}}
            return

        if "contentBlockStop" in event:
            # {'contentBlockStop': {'contentBlockIndex': 0}}
            return

        if "messageStop" in event:
            # {'messageStop': {'stopReason': 'end_turn'}}
            if stop_reason := event["messageStop"].get("stopReason"):
                self._response["stopReason"] = stop_reason
            return

        if "metadata" in event:
            # {'metadata': {'usage': {'inputTokens': 12, 'outputTokens': 15, 'totalTokens': 27}, 'metrics': {'latencyMs': 2980}}}
            if usage := event["metadata"].get("usage"):
                self._response["usage"] = {}
                if input_tokens := usage.get("inputTokens"):
                    self._response["usage"]["inputTokens"] = input_tokens

                if output_tokens := usage.get("outputTokens"):
                    self._response["usage"]["outputTokens"] = output_tokens

            self._stream_done_callback(self._response)
            return


# pylint: disable=abstract-method
class InvokeModelWithResponseStreamWrapper(ObjectProxy):
    """Wrapper for botocore.eventstream.EventStream"""

    def __init__(
        self,
        stream: EventStream,
        stream_done_callback: _StreamDoneCallableT,
        stream_error_callback: _StreamErrorCallableT,
        model_id: str,
    ):
        super().__init__(stream)

        self._stream_done_callback = stream_done_callback
        self._stream_error_callback = stream_error_callback
        self._model_id = model_id

        # accumulating things in the same shape of the Converse API
        # {"usage": {"inputTokens": 0, "outputTokens": 0}, "stopReason": "finish"}
        self._response = {}

    def __iter__(self):
        try:
            for event in self.__wrapped__:
                self._process_event(event)
                yield event
        except EventStreamError as exc:
            self._stream_error_callback(exc)
            raise

    def _process_event(self, event):
        if "chunk" not in event:
            return

        json_bytes = event["chunk"].get("bytes", b"")
        decoded = json_bytes.decode("utf-8")
        try:
            chunk = json.loads(decoded)
        except json.JSONDecodeError:
            return

        if "amazon.titan" in self._model_id:
            self._process_amazon_titan_chunk(chunk)
        elif "amazon.nova" in self._model_id:
            self._process_amazon_nova_chunk(chunk)
        elif "anthropic.claude" in self._model_id:
            self._process_anthropic_claude_chunk(chunk)

    def _process_invocation_metrics(self, invocation_metrics):
        self._response["usage"] = {}
        if input_tokens := invocation_metrics.get("inputTokenCount"):
            self._response["usage"]["inputTokens"] = input_tokens

        if output_tokens := invocation_metrics.get("outputTokenCount"):
            self._response["usage"]["outputTokens"] = output_tokens

    def _process_amazon_titan_chunk(self, chunk):
        if (stop_reason := chunk.get("completionReason")) is not None:
            self._response["stopReason"] = stop_reason

        if invocation_metrics := chunk.get("amazon-bedrock-invocationMetrics"):
            # "amazon-bedrock-invocationMetrics":{
            #     "inputTokenCount":9,"outputTokenCount":128,"invocationLatency":3569,"firstByteLatency":2180
            # }
            self._process_invocation_metrics(invocation_metrics)
            self._stream_done_callback(self._response)

    def _process_amazon_nova_chunk(self, chunk):
        if "messageStart" in chunk:
            # {'messageStart': {'role': 'assistant'}}
            return

        if "contentBlockDelta" in chunk:
            # {'contentBlockDelta': {'delta': {'text': "Hello"}, 'contentBlockIndex': 0}}
            return

        if "contentBlockStop" in chunk:
            # {'contentBlockStop': {'contentBlockIndex': 0}}
            return

        if "messageStop" in chunk:
            # {'messageStop': {'stopReason': 'end_turn'}}
            if stop_reason := chunk["messageStop"].get("stopReason"):
                self._response["stopReason"] = stop_reason
            return

        if "metadata" in chunk:
            # {'metadata': {'usage': {'inputTokens': 8, 'outputTokens': 117}, 'metrics': {}, 'trace': {}}}
            if usage := chunk["metadata"].get("usage"):
                self._response["usage"] = {}
                if input_tokens := usage.get("inputTokens"):
                    self._response["usage"]["inputTokens"] = input_tokens

                if output_tokens := usage.get("outputTokens"):
                    self._response["usage"]["outputTokens"] = output_tokens

            self._stream_done_callback(self._response)
            return

    def _process_anthropic_claude_chunk(self, chunk):
        # pylint: disable=too-many-return-statements
        if not (message_type := chunk.get("type")):
            return

        if message_type == "message_start":
            # {'type': 'message_start', 'message': {'id': 'id', 'type': 'message', 'role': 'assistant', 'model': 'claude-2.0', 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 18, 'output_tokens': 1}}}
            return

        if message_type == "content_block_start":
            # {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}
            return

        if message_type == "content_block_delta":
            # {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'Here'}}
            return

        if message_type == "content_block_stop":
            # {'type': 'content_block_stop', 'index': 0}
            return

        if message_type == "message_delta":
            # {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 123}}
            if (
                stop_reason := chunk.get("delta", {}).get("stop_reason")
            ) is not None:
                self._response["stopReason"] = stop_reason
            return

        if message_type == "message_stop":
            # {'type': 'message_stop', 'amazon-bedrock-invocationMetrics': {'inputTokenCount': 18, 'outputTokenCount': 123, 'invocationLatency': 5250, 'firstByteLatency': 290}}
            if invocation_metrics := chunk.get(
                "amazon-bedrock-invocationMetrics"
            ):
                self._process_invocation_metrics(invocation_metrics)
            self._stream_done_callback(self._response)
            return


def genai_capture_message_content() -> bool:
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )
    return capture_content.lower() == "true"


def message_to_event(message, capture_content):
    attributes = {GEN_AI_SYSTEM: GenAiSystemValues.AWS_BEDROCK.value}
    role = message.get("role")
    content = message.get("content")

    body = {}
    if capture_content and content:
        body["content"] = content
    if role == "assistant":
        # TODO
        """
        tool_calls = extract_tool_calls(message, capture_content)
        if tool_calls:
            body = {"tool_calls": tool_calls}
        """
    elif role == "tool":
        tool_call_id = message.get("tool_call_id")
        if tool_call_id:
            body["id"] = tool_call_id

    return Event(
        name=f"gen_ai.{role}.message",
        attributes=attributes,
        body=body if body else None,
    )
