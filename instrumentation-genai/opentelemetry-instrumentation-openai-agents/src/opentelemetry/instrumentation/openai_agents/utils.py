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

from typing import Optional

from .constants import GenAIOutputType, GenAIProvider, GenAIToolType


def get_agent_operation_name(operation: str) -> str:
    """Get the operation name for agent operations."""
    return f"openai_agents.{operation}"


def get_agent_span_name(operation: str, model: Optional[str] = None) -> str:
    """Get the span name for agent operations."""
    if model:
        return f"openai_agents {operation} {model}"
    return f"openai_agents {operation}"


# ---------------- Normalization / Validation Helpers ----------------


def normalize_provider(provider: Optional[str]) -> Optional[str]:
    """Normalize provider name to spec-compliant value."""
    if not provider:
        return None
    p = provider.strip().lower()
    if p in GenAIProvider.ALL:
        return p
    return provider  # passthrough if unknown (forward compat)


def validate_tool_type(tool_type: Optional[str]) -> str:
    """Validate and normalize tool type."""
    if not tool_type:
        return GenAIToolType.FUNCTION  # default
    t = tool_type.strip().lower()
    return t if t in GenAIToolType.ALL else GenAIToolType.FUNCTION


def normalize_output_type(output_type: Optional[str]) -> str:
    """Normalize output type to spec-compliant value."""
    if not output_type:
        return GenAIOutputType.TEXT  # default
    o = output_type.strip().lower()
    base_map = {
        "json_object": GenAIOutputType.JSON,
        "jsonschema": GenAIOutputType.JSON,
        "speech_audio": GenAIOutputType.SPEECH,
        "audio_speech": GenAIOutputType.SPEECH,
        "image_png": GenAIOutputType.IMAGE,
        "function_arguments_json": GenAIOutputType.JSON,
        "tool_call": GenAIOutputType.JSON,
        "transcription_json": GenAIOutputType.JSON,
    }
    if o in base_map:
        return base_map[o]
    if o in {
        GenAIOutputType.TEXT,
        GenAIOutputType.JSON,
        GenAIOutputType.IMAGE,
        GenAIOutputType.SPEECH,
    }:
        return o
    return GenAIOutputType.TEXT  # default for unknown
