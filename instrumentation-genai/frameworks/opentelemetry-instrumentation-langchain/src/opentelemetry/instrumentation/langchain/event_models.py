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

"""Event data models for LangChain instrumentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict


class _FunctionToolCall(TypedDict):
    """Represents a function call within a tool call."""

    function_name: str
    arguments: Optional[Dict[str, Any]]


class ToolCall(TypedDict):
    """Represents a tool call in the AI model."""

    id: str
    function: _FunctionToolCall
    type: Literal["function"]


class CompletionMessage(TypedDict):
    """Represents a message in the AI model."""

    content: Any
    role: str


@dataclass
class MessageEvent:
    """Represents an input message event for the AI model.

    Attributes:
        content: The message content.
        role: The role of the message sender (default: "user").
        tool_calls: Optional list of tool calls in the message.
    """

    content: Any
    role: str = "user"
    tool_calls: Optional[List[ToolCall]] = None


@dataclass
class ChoiceEvent:
    """Represents a completion choice event for the AI model.

    Attributes:
        index: The index of this choice in the response.
        message: The completion message content.
        finish_reason: The reason for completion (default: "unknown").
        tool_calls: Optional list of tool calls in the completion.
    """

    index: int
    message: CompletionMessage
    finish_reason: str = "unknown"
    tool_calls: Optional[List[ToolCall]] = field(default=None)
