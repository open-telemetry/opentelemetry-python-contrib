from dataclasses import dataclass, field
from typing import List


@dataclass
class ToolOutput:
    tool_call_id: str
    content: str

@dataclass
class ToolFunction:
    name: str
    description: str
    parameters: str

@dataclass
class ToolFunctionCall:
    id: str
    name: str
    arguments: str
    type: str

@dataclass
class Message:
    content: str
    type: str
    name: str
    tool_call_id: str
    tool_function_calls: List[ToolFunctionCall] = field(default_factory=list)

@dataclass
class ChatGeneration:
    content: str
    type: str
    finish_reason: str = None
    tool_function_calls: List[ToolFunctionCall] = field(default_factory=list)

@dataclass
class Error:
    message: str
    type: type[BaseException]