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

from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID
import time

from opentelemetry.genai.sdk.data import Message, ChatGeneration, ToolOutput, ToolFunction, ToolFunctionCall

@dataclass
class LLMInvocation:
    """
    Represents a single LLM call invocation.
    """
    run_id: UUID
    parent_run_id: Optional[UUID] = None
    start_time: float = field(default_factory=time.time)
    end_time: float = None
    messages: List[Message] = field(default_factory=list)
    chat_generations: List[ChatGeneration] = field(default_factory=list)
    tool_functions: List[ToolFunction] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    span_id: int = 0
    trace_id: int = 0

@dataclass
class ToolInvocation:
    """
    Represents a single Tool call invocation.
    """
    run_id: UUID
    output: ToolOutput = None
    parent_run_id: Optional[UUID] = None
    start_time: float = field(default_factory=time.time)
    end_time: float = None
    input_str: Optional[str] = None
    attributes: dict = field(default_factory=dict)