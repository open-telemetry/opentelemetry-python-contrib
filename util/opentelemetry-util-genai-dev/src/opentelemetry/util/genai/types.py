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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Type, Union
from uuid import UUID, uuid4

from opentelemetry.trace import Span
from opentelemetry.util.types import AttributeValue


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


@dataclass
class LLMInvocation:
    """
    Represents a single LLM call invocation.
    Added optional fields (run_id, parent_run_id, messages, chat_generations) to
    interoperate with advanced generators (SpanMetricGenerator, SpanMetricEventGenerator).
    """

    request_model: str
    # Stores either a contextvars Token or a context manager (use_span) kept open until finish/error.
    context_token: Optional[Any] = None
    span: Optional[Span] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    input_messages: List[InputMessage] = field(default_factory=list)
    output_messages: List[OutputMessage] = field(default_factory=list)
    provider: Optional[str] = None
    response_model_name: Optional[str] = None
    response_id: Optional[str] = None
    input_tokens: Optional[AttributeValue] = None
    output_tokens: Optional[AttributeValue] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Advanced generator compatibility fields
    run_id: UUID = field(default_factory=uuid4)
    parent_run_id: Optional[UUID] = None
    # Unified views expected by span_metric* generators
    messages: List[InputMessage] = field(default_factory=list)
    chat_generations: List[OutputMessage] = field(default_factory=list)


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


__all__ = [
    # existing exports intentionally implicit before; making explicit for new additions
    "ContentCapturingMode",
    "ToolCall",
    "ToolCallResponse",
    "Text",
    "InputMessage",
    "OutputMessage",
    "LLMInvocation",
    "Error",
    "EvaluationResult",
]
