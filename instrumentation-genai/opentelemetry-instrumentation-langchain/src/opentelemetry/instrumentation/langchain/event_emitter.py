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

"""Event emission for LangChain instrumentation."""

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Union

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.event_models import (
    ChoiceEvent,
    MessageEvent,
)
from opentelemetry.instrumentation.langchain.utils import (
    should_emit_events,
    should_send_prompts,
)


class Roles(Enum):
    """Valid roles for GenAI messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


VALID_MESSAGE_ROLES = {role.value for role in Roles}
"""The valid roles for naming the message event."""

EVENT_ATTRIBUTES = {GenAIAttributes.GEN_AI_SYSTEM: "langchain"}
"""The attributes to be used for the event."""


def emit_event(event: Union[MessageEvent, ChoiceEvent]) -> None:
    """Emit an event to the OpenTelemetry SDK.

    Args:
        event: The event to emit (MessageEvent or ChoiceEvent).

    Raises:
        TypeError: If the event type is not supported.
    """
    if not should_emit_events():
        return

    if isinstance(event, MessageEvent):
        _emit_message_event(event)
    elif isinstance(event, ChoiceEvent):
        _emit_choice_event(event)
    else:
        raise TypeError("Unsupported event type")


def _emit_message_event(event: MessageEvent) -> None:
    """Emit a message event.

    Args:
        event: The message event to emit.
    """
    body = asdict(event)

    if event.role in VALID_MESSAGE_ROLES:
        name = f"gen_ai.{event.role}.message"
        # According to the semantic conventions, the role is conditionally
        # required if available and not equal to the "role" in the message
        # name. So, remove the role from the body if it is the same as the
        # event name.
        body.pop("role", None)
    else:
        name = "gen_ai.user.message"

    # According to the semantic conventions, only the assistant role has
    # tool calls
    if event.role != Roles.ASSISTANT.value and event.tool_calls is not None:
        del body["tool_calls"]
    elif event.tool_calls is None:
        del body["tool_calls"]

    if not should_send_prompts():
        del body["content"]
        if body.get("tool_calls") is not None:
            for tool_call in body["tool_calls"]:
                tool_call["function"].pop("arguments", None)

    log_record = LogRecord(
        body=body,
        attributes=EVENT_ATTRIBUTES,
        event_name=name,
    )
    Config.event_logger.emit(log_record)  # type: ignore[union-attr]


def _emit_choice_event(event: ChoiceEvent) -> None:
    """Emit a choice event.

    Args:
        event: The choice event to emit.
    """
    body = asdict(event)
    if event.message["role"] == Roles.ASSISTANT.value:
        # According to the semantic conventions, the role is conditionally
        # required if available and not equal to "assistant", so remove the
        # role from the body if it is "assistant".
        body["message"].pop("role", None)

    if event.tool_calls is None:
        del body["tool_calls"]

    if not should_send_prompts():
        body["message"].pop("content", None)
        if body.get("tool_calls") is not None:
            for tool_call in body["tool_calls"]:
                tool_call["function"].pop("arguments", None)

    log_record = LogRecord(
        body=body,
        attributes=EVENT_ATTRIBUTES,
        event_name="gen_ai.choice",
    )
    Config.event_logger.emit(log_record)  # type: ignore[union-attr]
