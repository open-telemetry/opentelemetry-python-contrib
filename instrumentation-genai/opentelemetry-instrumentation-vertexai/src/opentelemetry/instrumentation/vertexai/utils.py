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
    Iterable,
    Mapping,
    Sequence,
    cast,
)
from urllib.parse import urlparse

from opentelemetry._events import Event
from opentelemetry.instrumentation.vertexai.events import (
    assistant_event,
    system_event,
    user_event,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.util.types import AnyValue, AttributeValue

if TYPE_CHECKING:
    from google.cloud.aiplatform_v1.types import content, tool
    from google.cloud.aiplatform_v1beta1.types import (
        content as content_v1beta1,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        tool as tool_v1beta1,
    )


@dataclass(frozen=True)
class GenerateContentParams:
    model: str
    contents: (
        Sequence[content.Content] | Sequence[content_v1beta1.Content] | None
    ) = None
    system_instruction: content.Content | content_v1beta1.Content | None = None
    tools: Sequence[tool.Tool] | Sequence[tool_v1beta1.Tool] | None = None
    tool_config: tool.ToolConfig | tool_v1beta1.ToolConfig | None = None
    labels: Mapping[str, str] | None = None
    safety_settings: (
        Sequence[content.SafetySetting]
        | Sequence[content_v1beta1.SafetySetting]
        | None
    ) = None
    generation_config: (
        content.GenerationConfig | content_v1beta1.GenerationConfig | None
    ) = None


def get_server_attributes(
    endpoint: str,
) -> dict[str, AttributeValue]:
    """Get server.* attributes from the endpoint, which is a hostname with optional port e.g.
    - ``us-central1-aiplatform.googleapis.com``
    - ``us-central1-aiplatform.googleapis.com:5431``
    """
    parsed = urlparse(f"scheme://{endpoint}")

    if not parsed.hostname:
        return {}

    return {
        server_attributes.SERVER_ADDRESS: parsed.hostname,
        server_attributes.SERVER_PORT: parsed.port or 443,
    }


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
    # Uncomment once GEN_AI_REQUEST_SEED is released in 1.30
    # https://github.com/open-telemetry/semantic-conventions/pull/1710
    # if "seed" in generation_config:
    #     attributes[GenAIAttributes.GEN_AI_REQUEST_SEED] = (
    #         generation_config.seed
    #     )
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


def get_span_name(span_attributes: Mapping[str, AttributeValue]) -> str:
    name = span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    model = span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    if not model:
        return f"{name}"
    return f"{name} {model}"


def request_to_events(
    *, params: GenerateContentParams, capture_content: bool
) -> Iterable[Event]:
    # System message
    if params.system_instruction:
        request_content = _parts_to_any_value(
            capture_content=capture_content,
            parts=params.system_instruction.parts,
        )
        yield system_event(
            role=params.system_instruction.role, content=request_content
        )

    for content in params.contents or []:
        # Assistant message
        if content.role == "model":
            request_content = _parts_to_any_value(
                capture_content=capture_content, parts=content.parts
            )

            yield assistant_event(role=content.role, content=request_content)
        # Assume user event but role should be "user"
        else:
            request_content = _parts_to_any_value(
                capture_content=capture_content, parts=content.parts
            )
            yield user_event(role=content.role, content=request_content)


def _parts_to_any_value(
    *,
    capture_content: bool,
    parts: Sequence[content.Part] | Sequence[content_v1beta1.Part],
) -> list[dict[str, AnyValue]] | None:
    if not capture_content:
        return None

    return [
        cast("dict[str, AnyValue]", type(part).to_dict(part))  # type: ignore[reportUnknownMemberType]
        for part in parts
    ]
