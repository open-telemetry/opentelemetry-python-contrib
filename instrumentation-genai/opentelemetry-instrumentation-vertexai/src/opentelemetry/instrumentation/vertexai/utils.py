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

from dataclasses import dataclass
from os import environ
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Mapping,
    Optional,
    TypedDict,
    cast,
)

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from vertexai.generative_models import Tool, ToolConfig
    from vertexai.generative_models._generative_models import (
        ContentsType,
        GenerationConfigType,
        SafetySettingsType,
        _GenerativeModel,
    )


@dataclass(frozen=True)
class GenerateContentParams:
    contents: ContentsType
    generation_config: Optional[GenerationConfigType]
    safety_settings: Optional[SafetySettingsType]
    tools: Optional[List["Tool"]]
    tool_config: Optional["ToolConfig"]
    labels: Optional[Dict[str, str]]
    stream: bool


class GenerationConfigDict(TypedDict, total=False):
    temperature: Optional[float]
    top_p: Optional[float]
    top_k: Optional[int]
    max_output_tokens: Optional[int]
    stop_sequences: Optional[List[str]]
    presence_penalty: Optional[float]
    frequency_penalty: Optional[float]
    seed: Optional[int]
    # And more fields which aren't needed yet


def get_genai_request_attributes(
    instance: _GenerativeModel,
    params: GenerateContentParams,
    operation_name: GenAIAttributes.GenAiOperationNameValues = GenAIAttributes.GenAiOperationNameValues.CHAT,
):
    model = _get_model_name(instance)
    generation_config = _get_generation_config(instance, params)
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.VERTEX_AI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: model,
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: generation_config.get(
            "temperature"
        ),
        GenAIAttributes.GEN_AI_REQUEST_TOP_P: generation_config.get("top_p"),
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: generation_config.get(
            "max_output_tokens"
        ),
        GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY: generation_config.get(
            "presence_penalty"
        ),
        GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY: generation_config.get(
            "frequency_penalty"
        ),
        GenAIAttributes.GEN_AI_OPENAI_REQUEST_SEED: generation_config.get(
            "seed"
        ),
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES: generation_config.get(
            "stop_sequences"
        ),
    }

    # filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


def _get_generation_config(
    instance: _GenerativeModel,
    params: GenerateContentParams,
) -> GenerationConfigDict:
    generation_config = params.generation_config or instance._generation_config
    if generation_config is None:
        return {}
    if isinstance(generation_config, dict):
        return cast(GenerationConfigDict, generation_config)
    return cast(GenerationConfigDict, generation_config.to_dict())


_RESOURCE_PREFIX = "publishers/google/models/"


def _get_model_name(instance: _GenerativeModel) -> str:
    model_name = instance._model_name

    # Can use str.removeprefix() once 3.8 is dropped
    if model_name.startswith(_RESOURCE_PREFIX):
        model_name = model_name[len(_RESOURCE_PREFIX) :]
    return model_name


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


def handle_span_exception(span: Span, error: Exception):
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()
