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


from contextvars import Token
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Type, Union

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
    id: Optional[str]
    type: Literal["tool_call"] = "tool_call"


@dataclass()
class ToolCallResponse:
    response: Any
    id: Optional[str]
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
    finish_reason: Union[str, FinishReason]


def _new_input_messages() -> List[InputMessage]:
    return []


def _new_output_messages() -> List[OutputMessage]:
    return []


def _new_str_any_dict() -> Dict[str, Any]:
    return {}


@dataclass
class LLMInvocation:
    """
    Represents a single LLM call invocation. When creating an LLMInvocation object,
    only update the data attributes. The span and context_token attributes are
    set by the TelemetryHandler.
    """

    request_model: str
    context_token: Optional[ContextToken] = None
    span: Optional[Span] = None
    input_messages: List[InputMessage] = field(
        default_factory=_new_input_messages
    )
    output_messages: List[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    provider: Optional[str] = None
    response_model_name: Optional[str] = None
    response_id: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    attributes: Dict[str, Any] = field(default_factory=_new_str_any_dict)
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    max_tokens: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    seed: Optional[int] = None


@dataclass
class Error:
    message: str
    type: Type[BaseException]
