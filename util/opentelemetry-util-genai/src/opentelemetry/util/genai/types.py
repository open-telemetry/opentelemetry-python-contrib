# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Type, Union

if TYPE_CHECKING:
    from opentelemetry.util.genai._inference_invocation import (  # pylint: disable=useless-import-alias
        LLMInvocation as LLMInvocation,  # noqa: PLC0414
    )
    from opentelemetry.util.genai._invocation import (  # pylint: disable=useless-import-alias
        GenAIInvocation as GenAIInvocation,  # noqa: PLC0414
    )


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
class GenericPart:
    """Used for provider-specific message part types that don't match
    the standard MessagePart types defined in semantic conventions. Wrap custom
    types with GenericPart(value=...) to explicitly opt-in to non-standard types.
    This will be removed in a future version when all instrumentations use core types."""

    value: Any
    type: Literal["generic"] = "generic"


@dataclass()
class ToolCallRequest:
    """Represents a tool call requested by the model (message part only).

    Use this for tool calls in message history. For execution tracking with spans
    and metrics, use ToolInvocation instead.

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
class ServerToolCall:
    """Represents a server-side tool call.

    Server tool calls are executed by the model provider on the server side rather
    than by the client application. Provider-specific tools (e.g., code_interpreter,
    web_search) can have well-defined schemas defined by the respective providers.

    This model is specified as part of semconv in `GenAI messages Python models - ServerToolCallPart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    name: str
    server_tool_call: Any
    id: str | None = None
    type: Literal["server_tool_call"] = "server_tool_call"


@dataclass()
class ServerToolCallResponse:
    """Represents a server-side tool call response.

    Contains the outcome and details of a server tool execution. Provider-specific
    tools (e.g., code_interpreter, web_search) can have well-defined response schemas
    defined by the respective providers.

    This model is specified as part of semconv in `GenAI messages Python models - ServerToolCallResponsePart
    <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/non-normative/models.ipynb>`__.
    """

    server_tool_call_response: Any
    id: str | None = None
    type: Literal["server_tool_call_response"] = "server_tool_call_response"


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


@dataclass()
class FunctionToolDefinition:
    """Represents a function tool definition sent to the model"""

    name: str
    description: str | None
    parameters: Any
    type: Literal["function"] = "function"


@dataclass()
class GenericToolDefinition:
    """Represents a generic tool definition sent to the model"""

    name: str
    type: str


ToolDefinition = Union[FunctionToolDefinition, GenericToolDefinition]

MessagePart = Union[
    Text,
    ToolCallRequest,
    ToolCallResponse,
    ServerToolCall,
    ServerToolCallResponse,
    Blob,
    File,
    Uri,
    Reasoning,
    GenericPart,  # For provider-specific types; prefer standard types above
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


@dataclass
class Error:
    message: str
    type: Type[BaseException]


def __getattr__(name: str) -> object:
    if name == "GenAIInvocation":
        import opentelemetry.util.genai.invocation as _inv  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        return _inv.GenAIInvocation
    if name == "LLMInvocation":
        from opentelemetry.util.genai._inference_invocation import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            LLMInvocation,
        )

        return LLMInvocation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
