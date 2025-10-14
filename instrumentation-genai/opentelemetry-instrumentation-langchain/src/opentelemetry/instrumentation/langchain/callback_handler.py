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

import json
from importlib import import_module
from types import SimpleNamespace
from typing import Any, Mapping, Protocol, Sequence, TypedDict, cast
from urllib.parse import urlparse
from uuid import UUID

from opentelemetry.instrumentation.langchain.span_manager import _SpanManager
from opentelemetry.trace import Span, Tracer

try:
    from langchain_core.callbacks import (
        BaseCallbackHandler,  # type: ignore[import]
    )
except ImportError:  # pragma: no cover - optional dependency
    BaseCallbackHandler = object  # type: ignore[assignment]


class _SerializedMessage(TypedDict, total=False):
    type: str
    content: Any
    additional_kwargs: Any
    response_metadata: Mapping[str, Any] | None
    tool_call_id: str
    tool_calls: Any
    usage_metadata: Mapping[str, Any] | None
    id: str
    name: str


class _MessageLike(Protocol):
    type: str

    @property
    def content(self) -> Any: ...

    def __getattr__(self, name: str) -> Any: ...


class _ChatGenerationLike(Protocol):
    message: _MessageLike | None
    generation_info: Mapping[str, Any] | None

    def __getattr__(self, name: str) -> Any: ...


class _LLMResultLike(Protocol):
    generations: Sequence[Sequence[_ChatGenerationLike]]
    llm_output: Mapping[str, Any] | None

    def __getattr__(self, name: str) -> Any: ...


try:
    _azure_attributes = import_module(
        "opentelemetry.semconv._incubating.attributes.azure_attributes"
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _azure_attributes = SimpleNamespace()

try:
    _gen_ai_attributes = import_module(
        "opentelemetry.semconv._incubating.attributes.gen_ai_attributes"
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _gen_ai_attributes = SimpleNamespace()

try:
    _openai_attributes = import_module(
        "opentelemetry.semconv._incubating.attributes.openai_attributes"
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _openai_attributes = SimpleNamespace()

GenAI = cast(Any, _gen_ai_attributes)
AZURE_RESOURCE_PROVIDER_NAMESPACE = cast(
    Any,
    getattr(
        _azure_attributes,
        "AZURE_RESOURCE_PROVIDER_NAMESPACE",
        "Microsoft.CognitiveServices",
    ),
)
OPENAI_REQUEST_SERVICE_TIER = cast(
    Any,
    getattr(
        _openai_attributes,
        "OPENAI_REQUEST_SERVICE_TIER",
        "genai.openai.request.service_tier",
    ),
)
OPENAI_RESPONSE_SERVICE_TIER = cast(
    Any,
    getattr(
        _openai_attributes,
        "OPENAI_RESPONSE_SERVICE_TIER",
        "genai.openai.response.service_tier",
    ),
)
OPENAI_RESPONSE_SYSTEM_FINGERPRINT = cast(
    Any,
    getattr(
        _openai_attributes,
        "OPENAI_RESPONSE_SYSTEM_FINGERPRINT",
        "genai.openai.response.system_fingerprint",
    ),
)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    _CHAT_MODEL_PROVIDER_MAPPING: dict[str, str] = {
        "ChatOpenAI": GenAI.GenAiProviderNameValues.OPENAI.value,
        "AzureChatOpenAI": GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
        "AzureOpenAI": GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
        "ChatBedrock": GenAI.GenAiProviderNameValues.AWS_BEDROCK.value,
        "BedrockChat": GenAI.GenAiProviderNameValues.AWS_BEDROCK.value,
    }

    _METADATA_PROVIDER_MAPPING: dict[str, str] = {
        "openai": GenAI.GenAiProviderNameValues.OPENAI.value,
        "azure": GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
        "azure_openai": GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
        "azure-ai-openai": GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
        "azure_ai_openai": GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
        "azure_ai_inference": GenAI.GenAiProviderNameValues.AZURE_AI_INFERENCE.value,
        "azure-inference": GenAI.GenAiProviderNameValues.AZURE_AI_INFERENCE.value,
        "amazon": GenAI.GenAiProviderNameValues.AWS_BEDROCK.value,
        "bedrock": GenAI.GenAiProviderNameValues.AWS_BEDROCK.value,
        "aws": GenAI.GenAiProviderNameValues.AWS_BEDROCK.value,
    }

    _SERVER_URL_KEYS = ("base_url", "azure_endpoint", "endpoint")

    def __init__(
        self,
        tracer: Tracer,
        capture_messages: bool,
    ) -> None:
        super().__init__()  # type: ignore

        self.span_manager = _SpanManager(
            tracer=tracer,
        )
        self._capture_messages = capture_messages

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: Sequence[Sequence[_MessageLike]],
        *,
        run_id: UUID,
        tags: list[str] | None,
        parent_run_id: UUID | None,
        metadata: dict[str, Any] | None,
        **kwargs: Any,
    ) -> None:
        provider_name = self._resolve_provider(
            serialized.get("name"), metadata
        )
        if provider_name is None:
            return

        kwargs_dict: dict[str, Any] = dict(kwargs)
        params = self._extract_params(kwargs_dict)
        request_model = self._extract_request_model(params, metadata)

        span = self.span_manager.create_chat_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            request_model=request_model,
        )

        span.set_attribute(GenAI.GEN_AI_PROVIDER_NAME, provider_name)
        if provider_name in (
            GenAI.GenAiProviderNameValues.AZURE_AI_OPENAI.value,
            GenAI.GenAiProviderNameValues.AZURE_AI_INFERENCE.value,
        ):
            span.set_attribute(
                AZURE_RESOURCE_PROVIDER_NAMESPACE,
                "Microsoft.CognitiveServices",
            )

        self._apply_request_attributes(span, params, metadata)

        if self._capture_messages and messages:
            serialized_messages = self._serialize_input_messages(messages)
            span.set_attribute(
                GenAI.GEN_AI_INPUT_MESSAGES,
                self._serialize_to_json(serialized_messages),
            )

    def _resolve_provider(
        self, llm_name: str | None, metadata: Mapping[str, Any] | None
    ) -> str | None:
        if llm_name:
            provider = self._CHAT_MODEL_PROVIDER_MAPPING.get(llm_name)
            if provider:
                return provider

        if metadata is None:
            return None

        provider_key = metadata.get("ls_provider")
        if not provider_key:
            return None

        mapped = self._METADATA_PROVIDER_MAPPING.get(provider_key.lower())
        if mapped is not None:
            return mapped

        return provider_key

    def _extract_params(
        self, kwargs: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        invocation_params = kwargs.get("invocation_params")
        if isinstance(invocation_params, Mapping):
            params = invocation_params.get("params") or invocation_params
            if isinstance(params, Mapping):
                return params
            return None

        return kwargs if kwargs else None

    def _extract_request_model(
        self,
        params: Mapping[str, Any] | None,
        metadata: Mapping[str, Any] | None,
    ) -> str | None:
        search_order = (
            "model_name",
            "model",
            "model_id",
            "ls_model_name",
            "azure_deployment",
            "deployment_name",
        )

        sources: list[Mapping[str, Any]] = []
        if isinstance(params, Mapping):
            sources.append(params)
        if isinstance(metadata, Mapping):
            sources.append(metadata)

        for key in search_order:
            for source in sources:
                value = source.get(key)
                if value:
                    return str(value)

        return None

    def _apply_request_attributes(
        self,
        span: Span,
        params: Mapping[str, Any] | None,
        metadata: Mapping[str, Any] | None,
    ) -> None:
        if params:
            top_p = params.get("top_p")
            if top_p is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_TOP_P, top_p)
            frequency_penalty = params.get("frequency_penalty")
            if frequency_penalty is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, frequency_penalty
                )
            presence_penalty = params.get("presence_penalty")
            if presence_penalty is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, presence_penalty
                )
            stop_sequences = params.get("stop")
            if stop_sequences is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, stop_sequences
                )
            seed = params.get("seed")
            if seed is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_SEED, seed)
            temperature = params.get("temperature")
            if temperature is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
                )
            max_tokens = params.get("max_completion_tokens") or params.get(
                "max_tokens"
            )
            if max_tokens is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)

            top_k = params.get("top_k")
            if top_k is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_TOP_K, top_k)

            choice_count = params.get("n") or params.get("choice_count")
            if choice_count is not None:
                try:
                    choice_value = int(choice_count)
                except (TypeError, ValueError):
                    choice_value = choice_count
                if choice_value != 1:
                    span.set_attribute(
                        GenAI.GEN_AI_REQUEST_CHOICE_COUNT, choice_value
                    )

            output_type = self._extract_output_type(params)
            if output_type is not None:
                span.set_attribute(GenAI.GEN_AI_OUTPUT_TYPE, output_type)

            service_tier = params.get("service_tier")
            if service_tier is not None:
                span.set_attribute(OPENAI_REQUEST_SERVICE_TIER, service_tier)

            self._maybe_set_server_attributes(span, params)

        if metadata:
            temperature = metadata.get("ls_temperature")
            if temperature is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
                )
            max_tokens = metadata.get("ls_max_tokens")
            if max_tokens is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)

    def _maybe_set_server_attributes(
        self, span: Span, params: Mapping[str, Any]
    ) -> None:
        potential_url = None
        for key in self._SERVER_URL_KEYS:
            value = params.get(key)
            if isinstance(value, str) and value:
                potential_url = value
                break

        if not potential_url:
            return

        parsed = urlparse(potential_url)
        hostname = parsed.hostname or potential_url
        if hostname:
            span.set_attribute("server.address", hostname)
            port = parsed.port
            if port is None:
                if parsed.scheme == "https":
                    port = 443
                elif parsed.scheme == "http":
                    port = 80
            if port is not None:
                span.set_attribute("server.port", port)

    def _extract_output_type(self, params: Mapping[str, Any]) -> str | None:
        response_format = params.get("response_format")
        output_type: str | None = None
        if isinstance(response_format, dict):
            output_type = response_format.get("type")
        elif isinstance(response_format, str):
            output_type = response_format

        if not output_type:
            return None

        lowered = output_type.lower()
        mapping = {
            "json_object": GenAI.GenAiOutputTypeValues.JSON.value,
            "json_schema": GenAI.GenAiOutputTypeValues.JSON.value,
            "json": GenAI.GenAiOutputTypeValues.JSON.value,
            "text": GenAI.GenAiOutputTypeValues.TEXT.value,
            "image": GenAI.GenAiOutputTypeValues.IMAGE.value,
            "speech": GenAI.GenAiOutputTypeValues.SPEECH.value,
        }

        return mapping.get(lowered)

    def _serialize_input_messages(
        self, messages: Sequence[Sequence[_MessageLike]]
    ) -> list[_SerializedMessage]:
        serialized: list[_SerializedMessage] = []
        for conversation in messages:
            for message in conversation:
                serialized.append(self._serialize_message(message))
        return serialized

    def _serialize_output_messages(
        self, response: _LLMResultLike
    ) -> list[_SerializedMessage]:
        serialized: list[_SerializedMessage] = []
        generations_attr = getattr(response, "generations", ())
        generations = cast(
            Sequence[Sequence[_ChatGenerationLike]], generations_attr
        )
        for generation in generations:
            for item in generation:
                message = cast(
                    _MessageLike | None, getattr(item, "message", None)
                )
                if message is not None:
                    serialized.append(self._serialize_message(message))
        return serialized

    def _serialize_message(self, message: _MessageLike) -> _SerializedMessage:
        payload: _SerializedMessage = {
            "type": getattr(message, "type", message.__class__.__name__),
            "content": getattr(message, "content", None),
        }
        for attr in (
            "additional_kwargs",
            "response_metadata",
            "tool_call_id",
            "tool_calls",
            "usage_metadata",
            "id",
            "name",
        ):
            value = getattr(message, attr, None)
            if value:
                payload[attr] = value
        return payload

    def _serialize_to_json(self, payload: Any) -> str:
        return json.dumps(payload, default=self._json_default)

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return value
        if isinstance(value, (list, tuple)):
            return list(value)
        return getattr(value, "__dict__", str(value))

    def on_llm_end(
        self,
        response: _LLMResultLike,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        **kwargs: Any,
    ) -> None:
        span = self.span_manager.get_span(run_id)

        if span is None:
            # If the span does not exist, we cannot set attributes or end it
            return

        generations_attr = getattr(response, "generations", ())
        generations = cast(
            Sequence[Sequence[_ChatGenerationLike]], generations_attr
        )

        finish_reasons: list[str] = []
        message_usage_metadata: Mapping[str, Any] | None
        for generation in generations:
            for chat_generation in generation:
                generation_info = cast(
                    Mapping[str, Any] | None,
                    getattr(chat_generation, "generation_info", None),
                )
                if generation_info is not None:
                    finish_reason = generation_info.get(
                        "finish_reason", "unknown"
                    )
                    if finish_reason is not None:
                        finish_reasons.append(str(finish_reason))
                message = cast(
                    _MessageLike | None,
                    getattr(chat_generation, "message", None),
                )
                if message is not None:
                    if generation_info is None and getattr(
                        message, "response_metadata", None
                    ):
                        response_metadata = cast(
                            Mapping[str, Any] | None,
                            getattr(message, "response_metadata", None),
                        )
                        finish_reason = (
                            response_metadata.get("stopReason", "unknown")
                            if response_metadata is not None
                            else "unknown"
                        )
                        if finish_reason is not None:
                            finish_reasons.append(str(finish_reason))
                    message_usage_metadata = cast(
                        Mapping[str, Any] | None,
                        getattr(message, "usage_metadata", None),
                    )
                    if message_usage_metadata:
                        input_tokens = message_usage_metadata.get(
                            "input_tokens", 0
                        )
                        output_tokens = message_usage_metadata.get(
                            "output_tokens", 0
                        )
                        span.set_attribute(
                            GenAI.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
                        )
                        span.set_attribute(
                            GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
                        )

        span.set_attribute(
            GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
        )

        llm_output = cast(
            Mapping[str, Any] | None, getattr(response, "llm_output", None)
        )
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get(
                "model"
            )
            if response_model is not None:
                span.set_attribute(
                    GenAI.GEN_AI_RESPONSE_MODEL, str(response_model)
                )

            response_id = llm_output.get("id")
            if response_id is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, str(response_id))

            service_tier = llm_output.get("service_tier")
            if service_tier is not None:
                span.set_attribute(OPENAI_RESPONSE_SERVICE_TIER, service_tier)

            system_fingerprint = llm_output.get("system_fingerprint")
            if system_fingerprint is not None:
                span.set_attribute(
                    OPENAI_RESPONSE_SYSTEM_FINGERPRINT, system_fingerprint
                )

        if self._capture_messages:
            serialized_outputs = self._serialize_output_messages(response)
            if serialized_outputs:
                span.set_attribute(
                    GenAI.GEN_AI_OUTPUT_MESSAGES,
                    self._serialize_to_json(serialized_outputs),
                )

        # End the LLM span
        self.span_manager.end_span(run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        **kwargs: Any,
    ) -> None:
        self.span_manager.handle_error(error, run_id)
