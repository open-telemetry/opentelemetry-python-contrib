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

from __future__ import annotations

import re
from dataclasses import dataclass
from os import environ
from typing import (
    TYPE_CHECKING,
    Mapping,
    Optional,
    Sequence,
)

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from google.cloud.aiplatform_v1.types import content, tool


@dataclass(frozen=True)
class GenerateContentParams:
    model: str
    contents: Optional[Sequence[content.Content]] = None
    system_instruction: Optional[content.Content | None] = None
    tools: Optional[Sequence[tool.Tool]] = None
    tool_config: Optional[tool.ToolConfig] = None
    labels: Optional[Mapping[str, str]] = None
    safety_settings: Optional[Sequence[content.SafetySetting]] = None
    generation_config: Optional[content.GenerationConfig] = None


def get_genai_request_attributes(
    params: GenerateContentParams,
    operation_name: GenAIAttributes.GenAiOperationNameValues = GenAIAttributes.GenAiOperationNameValues.CHAT,
):
    model = _get_model_name(params.model)
    generation_config = params.generation_config
    attributes: dict[str, AttributeValue] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.VERTEX_AI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: model,
    }

    if not generation_config:
        return attributes

    # Check for optional fields
    # https://proto-plus-python.readthedocs.io/en/stable/fields.html#optional-fields
    if "temperature" in generation_config:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] = (
            generation_config.temperature
        )
    if "top_p" in generation_config:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] = (
            generation_config.top_p
        )
    if "max_output_tokens" in generation_config:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] = (
            generation_config.max_output_tokens
        )
    if "presence_penalty" in generation_config:
        attributes[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] = (
            generation_config.presence_penalty
        )
    if "frequency_penalty" in generation_config:
        attributes[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] = (
            generation_config.frequency_penalty
        )
    if "seed" in generation_config:
        attributes[GenAIAttributes.GEN_AI_OPENAI_REQUEST_SEED] = (
            generation_config.seed
        )
    if "stop_sequences" in generation_config:
        attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] = (
            generation_config.stop_sequences
        )

    return attributes


_MODEL_STRIP_RE = re.compile(
    r"^projects/(.*)/locations/(.*)/publishers/google/models/"
)


def _get_model_name(model: str) -> str:
    return _MODEL_STRIP_RE.sub("", model)


OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)


def is_content_enabled() -> bool:
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )

    return capture_content.lower() == "true"


def get_span_name(span_attributes: Mapping[str, AttributeValue]):
    name = span_attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME, "")
    model = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, "")
    return f"{name} {model}"
