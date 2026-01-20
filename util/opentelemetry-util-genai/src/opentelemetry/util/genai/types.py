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

from contextvars import Token
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Type, Union

from typing_extensions import TypeAlias

from opentelemetry.context import Context
from opentelemetry.trace import Span

ContextToken: TypeAlias = Token[Context]


class ContentCapturingMode(Enum):
    # Do not capture content (default).
    NO_CONTENT = 0
    # Only capture content in spans.
    SPAN_ONLY = 1
    # Only capture content in events.
    EVENT_ONLY = 2
    # Capture content in both spans and events.
    SPAN_AND_EVENT = 3


@dataclass()
class ToolCall:
    arguments: Any
    name: str
    id: str | None
    type: Literal["tool_call"] = "tool_call"


@dataclass()
class ToolCallResponse:
    response: Any
    id: str | None
    type: Literal["tool_call_response"] = "tool_call_response"


FinishReason = Literal[
    "content_filter", "error", "length", "stop", "tool_calls"
]


@dataclass()
class Text:
    content: str
    type: Literal["text"] = "text"


MessagePart = Union[Text, ToolCall, ToolCallResponse, Any]


@dataclass()
class InputMessage:
    role: str
    parts: list[MessagePart]


@dataclass()
class OutputMessage:
    role: str
    parts: list[MessagePart]
    finish_reason: str | FinishReason


def _new_input_messages() -> list[InputMessage]:
    return []


def _new_output_messages() -> list[OutputMessage]:
    return []


def _new_str_any_dict() -> dict[str, Any]:
    return {}


@dataclass
class GenAIInvocation:
    context_token: ContextToken | None = None
    span: Span | None = None
    attributes: dict[str, Any] = field(default_factory=_new_str_any_dict)


@dataclass
class LLMInvocation(GenAIInvocation):
    """
    Represents a single LLM call invocation. When creating an LLMInvocation object,
    only update the data attributes. The span and context_token attributes are
    set by the TelemetryHandler.
    """

    request_model: str | None = None
    input_messages: list[InputMessage] = field(
        default_factory=_new_input_messages
    )
    output_messages: list[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    provider: str | None = None
    response_model_name: str | None = None
    response_id: str | None = None
    finish_reasons: list[str] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    seed: int | None = None
    # Monotonic start time in seconds (from timeit.default_timer) used
    # for duration calculations to avoid mixing clock sources. This is
    # populated by the TelemetryHandler when starting an invocation.
    monotonic_start_s: float | None = None


@dataclass
class Error:
    message: str
    type: Type[BaseException]
