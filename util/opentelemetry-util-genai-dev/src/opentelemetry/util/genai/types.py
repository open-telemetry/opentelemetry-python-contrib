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


import time
from contextvars import Token
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Type, Union
from uuid import UUID, uuid4

from opentelemetry.trace import Span
from opentelemetry.util.types import AttributeValue

ContextToken = Token  # simple alias; avoid TypeAlias warning tools


class ContentCapturingMode(Enum):
    # Do not capture content (default).
    NO_CONTENT = 0
    # Only capture content in spans.
    SPAN_ONLY = 1
    # Only capture content in events.
    EVENT_ONLY = 2
    # Capture content in both spans and events.
    SPAN_AND_EVENT = 3


def _new_input_messages() -> list["InputMessage"]:  # quotes for forward ref
    return []


def _new_output_messages() -> list["OutputMessage"]:  # quotes for forward ref
    return []


def _new_str_any_dict() -> dict[str, Any]:
    return {}


@dataclass()
class ToolCall:
    """Represents a single tool call invocation (Phase 4)."""

    arguments: Any
    name: str
    id: Optional[str]
    type: Literal["tool_call"] = "tool_call"
    # Optional fields for telemetry
    provider: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=_new_str_any_dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    span: Optional[Span] = None
    context_token: Optional[ContextToken] = None


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
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    input_messages: List[InputMessage] = field(
        default_factory=_new_input_messages
    )
    output_messages: List[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    # Added in composite refactor Phase 1 for backward compatibility with
    # generators that previously stashed normalized lists dynamically.
    # "messages" mirrors input_messages at start; "chat_generations" mirrors
    # output_messages. They can be overwritten by generators as needed without
    # risking AttributeError during lifecycle hooks.
    messages: List[InputMessage] = field(default_factory=_new_input_messages)
    chat_generations: List[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    provider: Optional[str] = None
    # Semantic-convention framework attribute (gen_ai.framework)
    framework: Optional[str] = None
    response_model_name: Optional[str] = None
    response_id: Optional[str] = None
    input_tokens: Optional[AttributeValue] = None
    output_tokens: Optional[AttributeValue] = None
    # Structured function/tool definitions for semantic convention emission
    request_functions: list[dict[str, Any]] = field(default_factory=list)
    # All non-semantic-convention or extended attributes (traceloop.*, request params, tool defs, etc.)
    attributes: Dict[str, Any] = field(default_factory=_new_str_any_dict)
    # Ahead of upstream
    run_id: UUID = field(default_factory=uuid4)
    parent_run_id: Optional[UUID] = None


@dataclass
class Error:
    message: str
    type: Type[BaseException]


@dataclass
class EvaluationResult:
    """Represents the outcome of a single evaluation metric.

    Additional fields (e.g., judge model, threshold) can be added without
    breaking callers that rely only on the current contract.
    """

    metric_name: str
    score: Optional[float] = None
    label: Optional[str] = None
    explanation: Optional[str] = None
    error: Optional[Error] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingInvocation:
    """Represents a single embedding model invocation (Phase 4 introduction).

    Kept intentionally minimal; shares a subset of fields with LLMInvocation so
    emitters can branch on isinstance without a separate protocol yet.
    """

    request_model: str
    input_texts: list[str] = field(default_factory=list)
    vector_dimensions: Optional[int] = None
    provider: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=_new_str_any_dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    span: Optional[Span] = None
    context_token: Optional[ContextToken] = None


__all__ = [
    # existing exports intentionally implicit before; making explicit for new additions
    "ContentCapturingMode",
    "ToolCall",
    "ToolCallResponse",
    "Text",
    "InputMessage",
    "OutputMessage",
    "LLMInvocation",
    "EmbeddingInvocation",
    "Error",
    "EvaluationResult",
    # backward compatibility normalization helpers
]
