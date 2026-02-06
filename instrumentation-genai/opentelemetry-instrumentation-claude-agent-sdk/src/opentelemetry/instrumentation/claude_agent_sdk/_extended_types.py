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

"""
Extended types for Claude Agent SDK instrumentation.

This module provides extended invocation types specifically for Claude Agent SDK
operations that are not covered by the standard OpenTelemetry GenAI types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Union
from opentelemetry.trace import Span

from opentelemetry.util.genai.types import (
    ContextToken,
    InputMessage,
    MessagePart,
    OutputMessage,
)



@dataclass
class FunctionToolDefinition:
    name: str
    description: str | None
    parameters: Any | None
    type: Literal["function"] = "function"

ToolDefinition = Union[FunctionToolDefinition, Any]


def _new_str_any_dict() -> Dict[str, Any]:
    """Helper function to create a new empty dict for default factory."""
    return {}


def _new_input_messages() -> List[InputMessage]:
    """Helper function to create a new empty list for default factory."""
    return []


def _new_output_messages() -> List[OutputMessage]:
    """Helper function to create a new empty list for default factory."""
    return []


def _new_tool_definitions() -> List[ToolDefinition]:
    """Helper function to create a new empty list for default factory."""
    return []


def _new_system_instruction() -> List[MessagePart]:
    """Helper function to create a new empty list for default factory."""
    return []


@dataclass
class ExecuteToolInvocation:
    """
    Represents a single tool execution invocation.
    
    When creating an ExecuteToolInvocation object, only update the data attributes.
    The span and context_token attributes are set by the TelemetryHandler.
    """

    tool_name: str
    context_token: ContextToken | None = None
    span: Span | None = None
    provider: str | None = None
    attributes: Dict[str, Any] = field(default_factory=_new_str_any_dict)
    # Tool-specific attributes
    tool_call_id: str | None = None
    tool_description: str | None = None
    tool_type: str | None = None  # function, extension, datastore
    tool_call_arguments: Any = None
    tool_call_result: Any = None
    monotonic_start_s: float | None = None


@dataclass
class InvokeAgentInvocation:
    """
    Represents a single agent invocation.
    
    When creating an InvokeAgentInvocation object, only update the data attributes.
    The span and context_token attributes are set by the TelemetryHandler.
    """

    provider: str
    context_token: ContextToken | None = None
    span: Span | None = None
    agent_name: str | None = None
    input_messages: List[InputMessage] = field(
        default_factory=_new_input_messages
    )
    output_messages: List[OutputMessage] = field(
        default_factory=_new_output_messages
    )
    tool_definitions: List[ToolDefinition] = field(
        default_factory=_new_tool_definitions
    )
    system_instruction: List[MessagePart] = field(
        default_factory=_new_system_instruction
    )
    attributes: Dict[str, Any] = field(default_factory=_new_str_any_dict)
    # Agent-specific attributes
    agent_id: str | None = None
    agent_description: str | None = None
    conversation_id: str | None = None
    data_source_id: str | None = None
    request_model: str | None = None
    response_model_name: str | None = None
    response_id: str | None = None
    finish_reasons: List[str] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Request parameters
    output_type: str | None = None
    choice_count: int | None = None
    seed: int | None = None
    frequency_penalty: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    stop_sequences: List[str] | None = None
    temperature: float | None = None
    top_p: float | None = None
    # Server information
    server_address: str | None = None
    server_port: int | None = None
    monotonic_start_s: float | None = None