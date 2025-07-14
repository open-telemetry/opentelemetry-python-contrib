from dataclasses import dataclass


@dataclass
class Message:
    content: str
    type: str

@dataclass
class ChatGeneration:
    content: str
    type: str
    finish_reason: str = None

@dataclass
class Error:
    message: str
    type: type[BaseException]