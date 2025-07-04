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

from google.protobuf import json_format

from opentelemetry._events import Event
from opentelemetry.instrumentation.vertexai.events import (
    ChoiceMessage,
    ChoiceToolCall,
    FinishReason,
    assistant_event,
    choice_event,
    system_event,
    tool_event,
    user_event,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.util.types import AnyValue, AttributeValue

if TYPE_CHECKING:
    from google.cloud.aiplatform_v1.types import (
        content,
        prediction_service,
        tool,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        content as content_v1beta1,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        prediction_service as prediction_service_v1beta1,
    )
    from google.cloud.aiplatform_v1beta1.types import (
        tool as tool_v1beta1,
    )


_MODEL = "model"


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


def get_genai_response_attributes(
    response: prediction_service.GenerateContentResponse
    | prediction_service_v1beta1.GenerateContentResponse,
) -> dict[str, AttributeValue]:
    finish_reasons: list[str] = [
        _map_finish_reason(candidate.finish_reason)
        for candidate in response.candidates
    ]
    # TODO: add gen_ai.response.id once available in the python client
    # https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3246
    return {
        GenAIAttributes.GEN_AI_RESPONSE_MODEL: response.model_version,
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS: finish_reasons,
        GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS: response.usage_metadata.prompt_token_count,
        GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS: response.usage_metadata.candidates_token_count,
    }


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
        if content.role == _MODEL:
            request_content = _parts_to_any_value(
                capture_content=capture_content, parts=content.parts
            )

            yield assistant_event(role=content.role, content=request_content)
            continue

        # Tool event
        #
        # Function call results can be parts inside of a user Content or in a separate Content
        # entry without a role. That may cause duplication in a user event, see
        # https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3280
        function_responses = [
            part.function_response
            for part in content.parts
            if "function_response" in part
        ]
        for idx, function_response in enumerate(function_responses):
            yield tool_event(
                id_=f"{function_response.name}_{idx}",
                role=content.role,
                content=json_format.MessageToDict(
                    function_response._pb.response
                )
                if capture_content
                else None,
            )

        if len(function_responses) == len(content.parts):
            # If the content only contained function responses, don't emit a user event
            continue

        request_content = _parts_to_any_value(
            capture_content=capture_content, parts=content.parts
        )
        yield user_event(role=content.role, content=request_content)


def response_to_events(
    *,
    response: prediction_service.GenerateContentResponse
    | prediction_service_v1beta1.GenerateContentResponse,
    capture_content: bool,
) -> Iterable[Event]:
    for candidate in response.candidates:
        tool_calls = _extract_tool_calls(
            candidate=candidate, capture_content=capture_content
        )

        # The original function_call Part is still duplicated in message, see
        # https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3280
        yield choice_event(
            finish_reason=_map_finish_reason(candidate.finish_reason),
            index=candidate.index,
            # default to "model" since Vertex uses that instead of assistant
            message=ChoiceMessage(
                role=candidate.content.role or _MODEL,
                content=_parts_to_any_value(
                    capture_content=capture_content,
                    parts=candidate.content.parts,
                ),
            ),
            tool_calls=tool_calls,
        )


def _extract_tool_calls(
    *,
    candidate: content.Candidate | content_v1beta1.Candidate,
    capture_content: bool,
) -> Iterable[ChoiceToolCall]:
    for idx, part in enumerate(candidate.content.parts):
        if "function_call" not in part:
            continue

        yield ChoiceToolCall(
            # Make up an id with index since vertex expects the indices to line up instead of
            # using ids.
            id=f"{part.function_call.name}_{idx}",
            function=ChoiceToolCall.Function(
                name=part.function_call.name,
                arguments=json_format.MessageToDict(
                    part.function_call._pb.args
                )
                if capture_content
                else None,
            ),
        )


def _parts_to_any_value(
    *,
    capture_content: bool,
    parts: Sequence[content.Part] | Sequence[content_v1beta1.Part],
) -> list[dict[str, AnyValue]] | None:
    if not capture_content:
        return None

    return [
        cast(
            "dict[str, AnyValue]",
            type(part).to_dict(part, including_default_value_fields=False),  # type: ignore[reportUnknownMemberType]
        )
        for part in parts
    ]


def _map_finish_reason(
    finish_reason: content.Candidate.FinishReason
    | content_v1beta1.Candidate.FinishReason,
) -> FinishReason | str:
    EnumType = type(finish_reason)  # pylint: disable=invalid-name
    if (
        finish_reason is EnumType.FINISH_REASON_UNSPECIFIED
        or finish_reason is EnumType.OTHER
    ):
        return "error"
    if finish_reason is EnumType.STOP:
        return "stop"
    if finish_reason is EnumType.MAX_TOKENS:
        return "length"

    # If there is no 1:1 mapping to an OTel preferred enum value, use the exact vertex reason
    return finish_reason.name
