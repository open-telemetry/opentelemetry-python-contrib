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
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
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
    """Represents a tool call requested by the model

    This model is specified as part of semconv in `GenAI messages Python models - ToolCallRequestPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    arguments: Any
    name: str
    id: str | None
    type: Literal["tool_call"] = "tool_call"


@dataclass()
class ToolCallResponse:
    """Represents a tool call result sent to the model or a built-in tool call outcome and details

    This model is specified as part of semconv in `GenAI messages Python models - ToolCallResponsePart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    response: Any
    id: str | None
    type: Literal["tool_call_response"] = "tool_call_response"


@dataclass()
class Text:
    """Represents text content sent to or received from the model

    This model is specified as part of semconv in `GenAI messages Python models - TextPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    content: str
    type: Literal["text"] = "text"


@dataclass()
class Reasoning:
    """Represents reasoning/thinking content received from the model

    This model is specified as part of semconv in `GenAI messages Python models - ReasoningPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    content: str
    type: Literal["reasoning"] = "reasoning"


Modality = Literal["image", "video", "audio"]


@dataclass()
class Blob:
    """Represents blob binary data sent inline to the model

    This model is specified as part of semconv in `GenAI messages Python models - BlobPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    mime_type: str | None
    modality: Union[Modality, str]
    content: bytes
    type: Literal["blob"] = "blob"


@dataclass()
class File:
    """Represents an external referenced file sent to the model by file id

    This model is specified as part of semconv in `GenAI messages Python models - FilePart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    mime_type: str | None
    modality: Union[Modality, str]
    file_id: str
    type: Literal["file"] = "file"


@dataclass()
class Uri:
    """Represents an external referenced file sent to the model by URI

    This model is specified as part of semconv in `GenAI messages Python models - UriPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    mime_type: str | None
    modality: Union[Modality, str]
    uri: str
    type: Literal["uri"] = "uri"


MessagePart = Union[
    Text, ToolCall, ToolCallResponse, Blob, File, Uri, Reasoning, Any
]


FinishReason = Literal[
    "content_filter", "error", "length", "stop", "tool_calls"
]


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


def _new_system_instruction() -> list[MessagePart]:
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
    # Chat by default
    operation_name: str = GenAI.GenAiOperationNameValues.CHAT.value
    input_messages: list[InputMessage] = field(
        default_factory=_new_input_messages
    )
    output_messages: list[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    system_instruction: list[MessagePart] = field(
        default_factory=_new_system_instruction
    )
    provider: str | None = None
    response_model_name: str | None = None
    response_id: str | None = None
    finish_reasons: list[str] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    attributes: dict[str, Any] = field(default_factory=_new_str_any_dict)
    """
    Additional attributes to set on spans and/or events. These attributes
    will not be set on metrics.
    """
    metric_attributes: dict[str, Any] = field(
        default_factory=_new_str_any_dict
    )
    """
    Additional attributes to set on metrics. Must be of a low cardinality.
    These attributes will not be set on spans or events.
    """
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    seed: int | None = None
    server_address: str | None = None
    server_port: int | None = None
    # Monotonic start time in seconds (from timeit.default_timer) used
    # for duration calculations to avoid mixing clock sources. This is
    # populated by the TelemetryHandler when starting an invocation.
    monotonic_start_s: float | None = None


@dataclass
class _BaseAgent(GenAIInvocation):
    """
    Shared base class for agent lifecycle types (AgentInvocation, AgentCreation).

    Contains fields common to all agent operations: identity, provider,
    model, system instructions, server info, and telemetry plumbing.

    Follows semconv for GenAI agent spans:
    https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md

    Do not instantiate directly — use AgentInvocation or AgentCreation.
    """

    # Agent identity
    agent_name: str | None = None
    agent_id: str | None = None
    agent_description: str | None = None
    agent_version: str | None = None

    # Operation
    operation_name: str = ""
    provider: str | None = None

    # Request
    request_model: str | None = None

    # Content (Opt-In)
    system_instruction: list[MessagePart] = field(
        default_factory=_new_system_instruction
    )

    # Server
    server_address: str | None = None
    server_port: int | None = None

    attributes: dict[str, Any] = field(default_factory=_new_str_any_dict)
    """
    Additional attributes to set on spans and/or events.
    """
    # Monotonic start time in seconds (from timeit.default_timer) used
    # for duration calculations to avoid mixing clock sources. This is
    # populated by the TelemetryHandler when starting an invocation.
    monotonic_start_s: float | None = None


@dataclass
class AgentCreation(_BaseAgent):
    """
    Represents agent creation/initialization (create_agent operation).

    Follows semconv for GenAI agent spans:
    https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#create-agent-span

    When creating an AgentCreation object, only update the data attributes.
    The span and context_token attributes are set by the TelemetryHandler.
    """

    # Override default operation name
    operation_name: str = "create_agent"


@dataclass
class AgentInvocation(_BaseAgent):
    """
    Represents an agent invocation (invoke_agent operation).

    Follows semconv for GenAI agent spans:
    https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-span

    When creating an AgentInvocation object, only update the data attributes.
    The span and context_token attributes are set by the TelemetryHandler.
    """

    # Override default operation name
    operation_name: str = "invoke_agent"

    # Invoke-specific request attributes (Cond. Required)
    conversation_id: str | None = None
    data_source_id: str | None = None
    output_type: str | None = None

    # Request parameters (Recommended)
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    seed: int | None = None
    choice_count: int | None = None

    # Response (Recommended)
    response_model_name: str | None = None
    response_id: str | None = None
    finish_reasons: list[str] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    # Content (Opt-In) — input/output messages and tool definitions
    input_messages: list[InputMessage] = field(
        default_factory=_new_input_messages
    )
    output_messages: list[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    tool_definitions: list[dict[str, Any]] | None = None

    # Span kind: CLIENT for remote agents, INTERNAL for in-process agents
    is_remote: bool = True

    metric_attributes: dict[str, Any] = field(
        default_factory=_new_str_any_dict
    )
    """
    Additional attributes to set on metrics. Must be of a low cardinality.
    These attributes will not be set on spans or events.
    """


@dataclass
class Error:
    message: str
    type: Type[BaseException]
