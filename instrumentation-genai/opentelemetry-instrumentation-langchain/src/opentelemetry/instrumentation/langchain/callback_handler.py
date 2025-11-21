# pyright: reportMissingImports=false

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
from collections.abc import Mapping, Sequence
from importlib import import_module
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast
from urllib.parse import urlparse
from uuid import UUID

from opentelemetry.instrumentation.langchain.span_manager import _SpanManager
from opentelemetry.trace import Span, Tracer

_TOOL_CALL_ARGUMENTS_ATTR = "gen_ai.tool.call.arguments"
_TOOL_CALL_RESULT_ATTR = "gen_ai.tool.call.result"
_TOOL_DEFINITIONS_ATTR = "gen_ai.tool.definitions"


class _BaseCallbackHandlerProtocol(Protocol):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    inheritable_handlers: Sequence[Any]

    def add_handler(self, handler: Any, inherit: bool = False) -> None: ...


class _BaseCallbackHandlerStub:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return

    inheritable_handlers: Sequence[Any] = ()

    def add_handler(self, handler: Any, inherit: bool = False) -> None:
        raise RuntimeError(
            "LangChain is required for the LangChain instrumentation."
        )


if TYPE_CHECKING:
    BaseCallbackHandler = _BaseCallbackHandlerProtocol
else:
    try:
        from langchain_core.callbacks import (
            BaseCallbackHandler,  # type: ignore[import]
        )
    except ImportError:  # pragma: no cover - optional dependency
        BaseCallbackHandler = _BaseCallbackHandlerStub


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


def _enum_member_value(enum_name: str, member_name: str, default: str) -> str:
    """Return the value for a GenAI enum member, falling back to the provided default."""
    enum_cls = getattr(GenAI, enum_name, None)
    member = (
        getattr(enum_cls, member_name, None) if enum_cls is not None else None
    )
    value = getattr(member, "value", None)
    if isinstance(value, str):
        return value
    if isinstance(member, str):
        return member
    return default


def _gen_ai_attr(name: str, default: str) -> Any:
    """Fetch a GenAI semantic attribute constant, defaulting to the provided string."""
    return getattr(GenAI, name, default)


_PROVIDER_OPENAI = _enum_member_value(
    "GenAiProviderNameValues", "OPENAI", "openai"
)
_PROVIDER_AZURE_OPENAI = _enum_member_value(
    "GenAiProviderNameValues", "AZURE_AI_OPENAI", "azure_ai_openai"
)
_PROVIDER_AZURE_INFERENCE = _enum_member_value(
    "GenAiProviderNameValues", "AZURE_AI_INFERENCE", "azure_ai_inference"
)
_PROVIDER_AWS_BEDROCK = _enum_member_value(
    "GenAiProviderNameValues", "AWS_BEDROCK", "aws_bedrock"
)

GEN_AI_PROVIDER_NAME_ATTR = _gen_ai_attr(
    "GEN_AI_PROVIDER_NAME", "gen_ai.provider.name"
)
GEN_AI_INPUT_MESSAGES_ATTR = _gen_ai_attr(
    "GEN_AI_INPUT_MESSAGES", "gen_ai.input.messages"
)
GEN_AI_OUTPUT_MESSAGES_ATTR = _gen_ai_attr(
    "GEN_AI_OUTPUT_MESSAGES", "gen_ai.output.messages"
)
GEN_AI_OUTPUT_TYPE_ATTR = _gen_ai_attr(
    "GEN_AI_OUTPUT_TYPE", "gen_ai.output.type"
)
GEN_AI_REQUEST_CHOICE_COUNT_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_CHOICE_COUNT", "gen_ai.request.choice.count"
)
GEN_AI_REQUEST_FREQUENCY_PENALTY_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_FREQUENCY_PENALTY", "gen_ai.request.frequency_penalty"
)
GEN_AI_REQUEST_MAX_TOKENS_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_MAX_TOKENS", "gen_ai.request.max_tokens"
)
GEN_AI_REQUEST_PRESENCE_PENALTY_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_PRESENCE_PENALTY", "gen_ai.request.presence_penalty"
)
GEN_AI_REQUEST_SEED_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_SEED", "gen_ai.request.seed"
)
GEN_AI_REQUEST_STOP_SEQUENCES_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_STOP_SEQUENCES", "gen_ai.request.stop_sequences"
)
GEN_AI_REQUEST_TEMPERATURE_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_TEMPERATURE", "gen_ai.request.temperature"
)
GEN_AI_REQUEST_TOP_K_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_TOP_K", "gen_ai.request.top_k"
)
GEN_AI_REQUEST_TOP_P_ATTR = _gen_ai_attr(
    "GEN_AI_REQUEST_TOP_P", "gen_ai.request.top_p"
)
GEN_AI_RESPONSE_FINISH_REASONS_ATTR = _gen_ai_attr(
    "GEN_AI_RESPONSE_FINISH_REASONS", "gen_ai.response.finish_reasons"
)
GEN_AI_RESPONSE_ID_ATTR = _gen_ai_attr(
    "GEN_AI_RESPONSE_ID", "gen_ai.response.id"
)
GEN_AI_RESPONSE_MODEL_ATTR = _gen_ai_attr(
    "GEN_AI_RESPONSE_MODEL", "gen_ai.response.model"
)
GEN_AI_TOOL_CALL_ID_ATTR = _gen_ai_attr(
    "GEN_AI_TOOL_CALL_ID", "gen_ai.tool.call.id"
)
GEN_AI_TOOL_TYPE_ATTR = _gen_ai_attr("GEN_AI_TOOL_TYPE", "gen_ai.tool.type")
GEN_AI_USAGE_INPUT_TOKENS_ATTR = _gen_ai_attr(
    "GEN_AI_USAGE_INPUT_TOKENS", "gen_ai.usage.input_tokens"
)
GEN_AI_USAGE_OUTPUT_TOKENS_ATTR = _gen_ai_attr(
    "GEN_AI_USAGE_OUTPUT_TOKENS", "gen_ai.usage.output_tokens"
)

_OUTPUT_TYPE_JSON = _enum_member_value("GenAiOutputTypeValues", "JSON", "json")
_OUTPUT_TYPE_TEXT = _enum_member_value("GenAiOutputTypeValues", "TEXT", "text")
_OUTPUT_TYPE_IMAGE = _enum_member_value(
    "GenAiOutputTypeValues", "IMAGE", "image"
)
_OUTPUT_TYPE_SPEECH = _enum_member_value(
    "GenAiOutputTypeValues", "SPEECH", "speech"
)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    _CHAT_MODEL_PROVIDER_MAPPING: dict[str, str] = {
        "ChatOpenAI": _PROVIDER_OPENAI,
        "AzureChatOpenAI": _PROVIDER_AZURE_OPENAI,
        "AzureOpenAI": _PROVIDER_AZURE_OPENAI,
        "ChatBedrock": _PROVIDER_AWS_BEDROCK,
        "BedrockChat": _PROVIDER_AWS_BEDROCK,
    }

    _METADATA_PROVIDER_MAPPING: dict[str, str] = {
        "openai": _PROVIDER_OPENAI,
        "azure": _PROVIDER_AZURE_OPENAI,
        "azure_openai": _PROVIDER_AZURE_OPENAI,
        "azure-ai-openai": _PROVIDER_AZURE_OPENAI,
        "azure_ai_openai": _PROVIDER_AZURE_OPENAI,
        "azure_ai_inference": _PROVIDER_AZURE_INFERENCE,
        "azure-inference": _PROVIDER_AZURE_INFERENCE,
        "amazon": _PROVIDER_AWS_BEDROCK,
        "bedrock": _PROVIDER_AWS_BEDROCK,
        "aws": _PROVIDER_AWS_BEDROCK,
    }

    _SERVER_URL_KEYS = ("base_url", "azure_endpoint", "endpoint")

    def __init__(
        self,
        tracer: Tracer,
        capture_messages: bool,
    ) -> None:
        base_init: Any = getattr(super(), "__init__", None)
        if callable(base_init):
            base_init()

        self.span_manager: _SpanManager = _SpanManager(
            tracer=tracer,
        )
        self._capture_messages = capture_messages
        self._metadata_provider_mapping = self._METADATA_PROVIDER_MAPPING

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

        span.set_attribute(GEN_AI_PROVIDER_NAME_ATTR, provider_name)
        if provider_name in (
            _PROVIDER_AZURE_OPENAI,
            _PROVIDER_AZURE_INFERENCE,
        ):
            span.set_attribute(
                AZURE_RESOURCE_PROVIDER_NAMESPACE,
                "Microsoft.CognitiveServices",
            )

        self._apply_request_attributes(span, params, metadata)

        if self._capture_messages:
            tool_definitions = self._extract_tool_definitions(
                params=params,
                metadata=metadata,
                serialized=serialized,
                extras=kwargs_dict,
            )
            if tool_definitions is not None:
                serialized_definitions = self._serialize_tool_payload(
                    tool_definitions
                )
                if serialized_definitions is not None:
                    span.set_attribute(
                        _TOOL_DEFINITIONS_ATTR, serialized_definitions
                    )

        if self._capture_messages and messages:
            serialized_messages = self._serialize_input_messages(messages)
            span.set_attribute(
                GEN_AI_INPUT_MESSAGES_ATTR,
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

    def _extract_params(self, kwargs: Mapping[str, Any]) -> dict[str, Any]:
        invocation_params = kwargs.get("invocation_params")
        if isinstance(invocation_params, Mapping):
            invocation_mapping = cast(Mapping[str, Any], invocation_params)
            params_raw = cast(
                Mapping[Any, Any] | None, invocation_mapping.get("params")
            )
            if isinstance(params_raw, Mapping):
                params_mapping = params_raw
                extracted: dict[str, Any] = {}
                for key, value in params_mapping.items():
                    key_str = key if isinstance(key, str) else str(key)
                    extracted[key_str] = value
                return extracted
            invocation_mapping = cast(Mapping[Any, Any], invocation_params)
            extracted: dict[str, Any] = {}
            for key, value in invocation_mapping.items():
                key_str = key if isinstance(key, str) else str(key)
                extracted[key_str] = value
            return extracted

        extracted: dict[str, Any] = {}
        for key, value in kwargs.items():
            extracted[key] = value
        return extracted

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
        params: dict[str, Any] | None,
        metadata: Mapping[str, Any] | None,
    ) -> None:
        if params:
            top_p = params.get("top_p")
            if top_p is not None:
                span.set_attribute(GEN_AI_REQUEST_TOP_P_ATTR, top_p)
            frequency_penalty = params.get("frequency_penalty")
            if frequency_penalty is not None:
                span.set_attribute(
                    GEN_AI_REQUEST_FREQUENCY_PENALTY_ATTR, frequency_penalty
                )
            presence_penalty = params.get("presence_penalty")
            if presence_penalty is not None:
                span.set_attribute(
                    GEN_AI_REQUEST_PRESENCE_PENALTY_ATTR, presence_penalty
                )
            stop_sequences = params.get("stop")
            if stop_sequences is not None:
                span.set_attribute(
                    GEN_AI_REQUEST_STOP_SEQUENCES_ATTR, stop_sequences
                )
            seed = params.get("seed")
            if seed is not None:
                span.set_attribute(GEN_AI_REQUEST_SEED_ATTR, seed)
            temperature = params.get("temperature")
            if temperature is not None:
                span.set_attribute(
                    GEN_AI_REQUEST_TEMPERATURE_ATTR, temperature
                )
            max_tokens = params.get("max_completion_tokens") or params.get(
                "max_tokens"
            )
            if max_tokens is not None:
                span.set_attribute(GEN_AI_REQUEST_MAX_TOKENS_ATTR, max_tokens)

            top_k = params.get("top_k")
            if top_k is not None:
                span.set_attribute(GEN_AI_REQUEST_TOP_K_ATTR, top_k)

            choice_count = params.get("n") or params.get("choice_count")
            if choice_count is not None:
                try:
                    choice_value = int(choice_count)
                except (TypeError, ValueError):
                    choice_value = choice_count
                if choice_value != 1:
                    span.set_attribute(
                        GEN_AI_REQUEST_CHOICE_COUNT_ATTR, choice_value
                    )

            output_type = self._extract_output_type(params)
            if output_type is not None:
                span.set_attribute(GEN_AI_OUTPUT_TYPE_ATTR, output_type)

            service_tier = params.get("service_tier")
            if service_tier is not None:
                span.set_attribute(OPENAI_REQUEST_SERVICE_TIER, service_tier)

            self._maybe_set_server_attributes(span, params)

        if metadata:
            temperature = metadata.get("ls_temperature")
            if temperature is not None:
                span.set_attribute(
                    GEN_AI_REQUEST_TEMPERATURE_ATTR, temperature
                )
            max_tokens = metadata.get("ls_max_tokens")
            if max_tokens is not None:
                span.set_attribute(GEN_AI_REQUEST_MAX_TOKENS_ATTR, max_tokens)

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
        if isinstance(response_format, Mapping):
            response_mapping = cast(Mapping[Any, Any], response_format)
            candidate: Any = response_mapping.get("type")
            if isinstance(candidate, str):
                output_type = candidate
            elif candidate is not None:
                output_type = str(candidate)
        elif isinstance(response_format, str):
            output_type = response_format
        elif response_format is not None:
            output_type = str(response_format)

        if not output_type:
            return None

        lowered = output_type.lower()
        mapping = {
            "json_object": _OUTPUT_TYPE_JSON,
            "json_schema": _OUTPUT_TYPE_JSON,
            "json": _OUTPUT_TYPE_JSON,
            "text": _OUTPUT_TYPE_TEXT,
            "image": _OUTPUT_TYPE_IMAGE,
            "speech": _OUTPUT_TYPE_SPEECH,
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
        payload: dict[str, Any] = {
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
            if value is not None:
                payload[attr] = value
        return cast(_SerializedMessage, payload)

    def _serialize_to_json(self, payload: Any) -> str:
        return json.dumps(payload, default=self._json_default)

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
        if isinstance(value, (list, tuple)):
            seq_value = cast(Sequence[Any], value)
            return [
                OpenTelemetryLangChainCallbackHandler._json_default(item)
                for item in seq_value
            ]
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
                            GEN_AI_USAGE_INPUT_TOKENS_ATTR, input_tokens
                        )
                        span.set_attribute(
                            GEN_AI_USAGE_OUTPUT_TOKENS_ATTR, output_tokens
                        )

        span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS_ATTR, finish_reasons)

        llm_output = cast(
            Mapping[str, Any] | None, getattr(response, "llm_output", None)
        )
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get(
                "model"
            )
            if response_model is not None:
                span.set_attribute(
                    GEN_AI_RESPONSE_MODEL_ATTR, str(response_model)
                )

            response_id = llm_output.get("id")
            if response_id is not None:
                span.set_attribute(GEN_AI_RESPONSE_ID_ATTR, str(response_id))

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
                    GEN_AI_OUTPUT_MESSAGES_ATTR,
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

    def on_tool_start(
        self,
        serialized: Mapping[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        metadata: Mapping[str, Any] | None = None,
        inputs: Mapping[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = self._resolve_tool_name(serialized, metadata, inputs)

        span = cast(
            Span,
            self.span_manager.create_tool_span(  # type: ignore[attr-defined]
                run_id=run_id,
                parent_run_id=parent_run_id,
                tool_name=tool_name,
            ),
        )

        provider_name = self._resolve_provider(None, metadata)
        if provider_name:
            span.set_attribute(GEN_AI_PROVIDER_NAME_ATTR, provider_name)

        tool_call_id = self._resolve_tool_call_id(metadata, inputs)
        if tool_call_id:
            span.set_attribute(GEN_AI_TOOL_CALL_ID_ATTR, tool_call_id)

        tool_type = self._resolve_tool_type(serialized, metadata)
        if tool_type:
            span.set_attribute(GEN_AI_TOOL_TYPE_ATTR, tool_type)

        if self._capture_messages:
            arguments_payload = self._serialize_tool_payload(
                inputs if inputs is not None else input_str
            )
            if arguments_payload is not None:
                span.set_attribute(
                    _TOOL_CALL_ARGUMENTS_ATTR, arguments_payload
                )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        **kwargs: Any,
    ) -> None:
        span = self.span_manager.get_span(run_id)
        if span is not None and self._capture_messages:
            result_payload = self._serialize_tool_payload(output)
            if result_payload is not None:
                span.set_attribute(_TOOL_CALL_RESULT_ATTR, result_payload)
        self.span_manager.end_span(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        **kwargs: Any,
    ) -> None:
        self.span_manager.handle_error(error, run_id)

    def _resolve_tool_name(
        self,
        serialized: Mapping[str, Any] | None,
        metadata: Mapping[str, Any] | None,
        inputs: Mapping[str, Any] | None,
    ) -> str | None:
        candidates: list[Any] = []
        if serialized:
            candidates.extend(
                [
                    serialized.get("name"),
                    serialized.get("id"),
                    cast(Mapping[str, Any], serialized.get("kwargs", {})).get(
                        "name"
                    )
                    if isinstance(serialized.get("kwargs"), Mapping)
                    else None,
                ]
            )
        if inputs:
            candidates.extend([inputs.get("tool"), inputs.get("name")])
        if metadata:
            candidates.extend(
                [
                    metadata.get("tool_name"),
                    metadata.get("agent_name"),
                ]
            )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    def _resolve_tool_call_id(
        self,
        metadata: Mapping[str, Any] | None,
        inputs: Mapping[str, Any] | None,
    ) -> str | None:
        def _extract(source: Mapping[str, Any]) -> str | None:
            for key in ("tool_call_id", "id", "call_id"):
                value = cast(Any, source.get(key))
                if value is None:
                    continue
                if isinstance(value, Mapping):
                    nested_mapping = cast(Mapping[str, Any], value)
                    nested_id = nested_mapping.get("id")
                    if nested_id:
                        return str(nested_id)
                    continue
                return str(value)
            tool_call = cast(Any, source.get("tool_call"))
            if isinstance(tool_call, Mapping):
                nested_mapping = cast(Mapping[str, Any], tool_call)
                nested = nested_mapping.get("id")
                if nested:
                    return str(nested)
            return None

        for container in (metadata, inputs):
            if isinstance(container, Mapping):
                extracted = _extract(container)
                if extracted:
                    return extracted
        return None

    def _resolve_tool_type(
        self,
        serialized: Mapping[str, Any] | None,
        metadata: Mapping[str, Any] | None,
    ) -> str | None:
        candidates: list[Any] = []
        if serialized:
            candidates.extend(
                [
                    serialized.get("type"),
                    cast(Mapping[str, Any], serialized.get("kwargs", {})).get(
                        "type"
                    )
                    if isinstance(serialized.get("kwargs"), Mapping)
                    else None,
                ]
            )
        if metadata:
            candidates.append(metadata.get("tool_type"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    def _serialize_tool_payload(self, payload: Any) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        try:
            return json.dumps(payload, default=self._json_default)
        except (TypeError, ValueError):
            return str(payload)
        except Exception:
            return None

    def _extract_tool_definitions(
        self,
        *,
        params: Mapping[str, Any] | None,
        metadata: Mapping[str, Any] | None,
        serialized: Mapping[str, Any] | None,
        extras: Mapping[str, Any] | None,
    ) -> Any:
        for source in (params, metadata, extras):
            if isinstance(source, Mapping):
                mapping_source: Mapping[str, Any] = source
                candidate = cast(Any, mapping_source.get("tools"))
                if candidate is not None:
                    return candidate
        if isinstance(serialized, Mapping):
            kwargs_mapping = serialized.get("kwargs")
            if isinstance(kwargs_mapping, Mapping):
                kwargs_typed = cast(Mapping[str, Any], kwargs_mapping)
                candidate = cast(Any, kwargs_typed.get("tools"))
                if candidate is not None:
                    return candidate
        return None
