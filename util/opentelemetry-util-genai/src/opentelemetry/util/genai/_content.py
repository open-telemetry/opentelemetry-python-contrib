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

"""Shared content serialization helpers for invocation types.

This module provides shared logic for serializing input/output messages,
system instructions, and tool definitions into span and event attributes.
Used by both InferenceInvocation and AgentInvocation to avoid duplication.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Sequence

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    MessagePart,
    OutputMessage,
    ToolDefinition,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
)


def _get_content_attributes(
    *,
    input_messages: Sequence[InputMessage],
    output_messages: Sequence[OutputMessage],
    system_instruction: Sequence[MessagePart],
    tool_definitions: Sequence[ToolDefinition] | None,
    for_span: bool,
) -> dict[str, Any]:
    """Serialize messages, system instructions, and tool definitions into attributes.

    Args:
        input_messages: Input messages to serialize.
        output_messages: Output messages to serialize.
        system_instruction: System instructions to serialize.
        tool_definitions: Tool definitions to serialize (may be None).
        for_span: If True, serialize for span attributes (JSON string);
                  if False, serialize for event attributes (list of dicts).
    """
    if not is_experimental_mode():
        return {}

    mode = get_content_capturing_mode()
    allowed_modes = (
        (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
        if for_span
        else (
            ContentCapturingMode.EVENT_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
    )
    if mode not in allowed_modes:
        return {}

    def serialize(items: Sequence[Any]) -> Any:
        dicts = [asdict(item) for item in items]
        return gen_ai_json_dumps(dicts) if for_span else dicts

    optional_attrs = (
        (
            GenAI.GEN_AI_INPUT_MESSAGES,
            serialize(input_messages) if input_messages else None,
        ),
        (
            GenAI.GEN_AI_OUTPUT_MESSAGES,
            serialize(output_messages) if output_messages else None,
        ),
        (
            GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
            serialize(system_instruction) if system_instruction else None,
        ),
        (
            GenAI.GEN_AI_TOOL_DEFINITIONS,
            serialize(tool_definitions) if tool_definitions else None,
        ),
    )
    return {key: value for key, value in optional_attrs if value is not None}
