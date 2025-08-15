from dataclasses import dataclass


@dataclass
class Message:
    content: str
    type: str
    name: str
    tool_call_id: str


@dataclass
class ChatGeneration:
    content: str
    type: str
    finish_reason: str = None


@dataclass
class Error:
    message: str
    type: type[BaseException]
