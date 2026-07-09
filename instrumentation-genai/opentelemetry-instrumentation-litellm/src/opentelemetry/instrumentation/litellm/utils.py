# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any, Iterable, List, Mapping

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import (
    EmbeddingInvocation,
    InferenceInvocation,
)
from opentelemetry.util.genai.types import (
    FunctionToolDefinition,
    InputMessage,
    OutputMessage,
    Text,
    ToolCallRequest,
    ToolCallResponse,
    ToolDefinition,
)

# Fallback ``gen_ai.provider.name`` value used when the provider cannot be
# resolved from the response or the model prefix. ``gen_ai.provider.name`` is
# ``anyOf [enum, string]`` in semconv, so a litellm-specific literal is a valid
# value when no upstream well-known one applies.
_LITELLM_PROVIDER = "litellm"

_CHAT = GenAIAttributes.GenAiOperationNameValues.CHAT.value
_EMBEDDINGS = GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value

# LiteLLM provider prefixes whose names differ from the OTel
# ``gen_ai.provider.name`` well-known values. Normalizing here keeps litellm
# spans/metrics under the same provider key as the rest of the repo. Unknown
# prefixes pass through unchanged (``gen_ai.provider.name`` is ``anyOf
# [enum, string]``).
_ProviderName = GenAIAttributes.GenAiProviderNameValues
_PROVIDER_ALIASES = {
    "azure": _ProviderName.AZURE_AI_OPENAI.value,
    "azure_ai": _ProviderName.AZURE_AI_INFERENCE.value,
    "bedrock": _ProviderName.AWS_BEDROCK.value,
    "vertex_ai": _ProviderName.GCP_VERTEX_AI.value,
    "gemini": _ProviderName.GCP_GEMINI.value,
    "mistral": _ProviderName.MISTRAL_AI.value,
}

# LiteLLM normalizes provider finish reasons to OpenAI values; map the ones
# that differ from the OTel GenAI vocabulary (``tool_calls`` -> ``tool_call``).
_FINISH_REASON_MAP = {
    "tool_calls": "tool_call",
    "function_call": "tool_call",
}


def get_property_value(obj: Any, property_name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def _normalize_provider(provider: str | None) -> str | None:
    if not provider:
        return provider
    return _PROVIDER_ALIASES.get(provider, provider)


def resolve_provider_from_kwargs(
    kwargs: Mapping[str, Any], args: tuple[Any, ...] = ()
) -> str:
    """Resolve ``gen_ai.provider.name`` from the request args/kwargs.

    Prefers an explicit ``custom_llm_provider`` kwarg, then the provider
    prefix on the ``provider/model`` model string, and finally falls back to
    the litellm-specific literal ``"litellm"`` for bare models whose provider
    is only known after the response is returned. The model may be passed
    positionally, so ``args`` is consulted the same way ``get_model`` does.
    """
    provider = kwargs.get("custom_llm_provider")
    if provider:
        return _normalize_provider(provider) or _LITELLM_PROVIDER
    model = get_model(args, kwargs)
    if "/" in model:
        return _normalize_provider(model.split("/", 1)[0]) or _LITELLM_PROVIDER
    return _LITELLM_PROVIDER


def resolve_provider_from_response(response: Any) -> str | None:
    """Resolve ``gen_ai.provider.name`` from a litellm ``ModelResponse``.

    LiteLLM records the resolved back-end under
    ``response._hidden_params["custom_llm_provider"]``.
    """
    hidden = getattr(response, "_hidden_params", None) or {}
    if isinstance(hidden, Mapping):
        return _normalize_provider(hidden.get("custom_llm_provider"))
    return None


def map_finish_reason(reason: str | None) -> str:
    if not reason:
        return "error"
    return _FINISH_REASON_MAP.get(reason, reason)


def is_streaming(kwargs: Mapping[str, Any]) -> bool:
    return bool(kwargs.get("stream"))


def get_model(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str:
    model = kwargs.get("model")
    if model is None and args:
        model = args[0]
    return model or ""


def _get_messages(
    args: tuple[Any, ...], kwargs: Mapping[str, Any]
) -> Iterable[Any]:
    messages = kwargs.get("messages")
    if messages is None and len(args) > 1:
        messages = args[1]
    return messages or []


def _is_text_part(content: Any) -> bool:
    return isinstance(content, str)


def extract_tool_calls(
    tool_calls: Iterable[Any],
) -> list[ToolCallRequest]:
    parts: list[ToolCallRequest] = []
    for tool_call in tool_calls:
        call_id = get_property_value(tool_call, "id")

        func_name = ""
        arguments: Any = None
        func = get_property_value(tool_call, "function")
        if func:
            func_name = get_property_value(func, "name") or ""
            arguments_str = get_property_value(func, "arguments")
            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except (json.JSONDecodeError, TypeError):
                    arguments = arguments_str

        parts.append(
            ToolCallRequest(id=call_id, name=func_name, arguments=arguments)
        )
    return parts


def prepare_input_messages(
    messages: Iterable[Any],
) -> List[InputMessage]:
    chat_messages: list[InputMessage] = []
    for message in messages:
        role = get_property_value(message, "role")
        chat_message = InputMessage(role=str(role), parts=[])
        chat_messages.append(chat_message)

        content = get_property_value(message, "content")

        if role == "assistant":
            tool_calls = get_property_value(message, "tool_calls")
            if tool_calls:
                chat_message.parts += extract_tool_calls(tool_calls)
            if _is_text_part(content):
                chat_message.parts.append(Text(content=str(content)))

        elif role == "tool":
            tool_call_id = get_property_value(message, "tool_call_id")
            chat_message.parts.append(
                ToolCallResponse(id=tool_call_id, response=content)
            )

        else:
            # system, user, fallback
            if _is_text_part(content):
                chat_message.parts.append(Text(content=str(content)))
    return chat_messages


def prepare_tool_definitions(
    tools: Iterable[Any] | None,
) -> list[ToolDefinition] | None:
    if not tools:
        return None

    definitions: list[ToolDefinition] = []
    for tool in tools:
        tool_type = get_property_value(tool, "type")
        if tool_type == "function":
            func = get_property_value(tool, "function")
            if func:
                definitions.append(
                    FunctionToolDefinition(
                        name=get_property_value(func, "name") or "",
                        description=get_property_value(func, "description"),
                        parameters=get_property_value(func, "parameters"),
                    )
                )
    return definitions


def prepare_output_messages(
    choices: Iterable[Any],
) -> List[OutputMessage]:
    output_messages: list[OutputMessage] = []
    for choice in choices:
        message = get_property_value(choice, "message")
        if not message:
            continue
        parts: list[Any] = []
        tool_calls = get_property_value(message, "tool_calls")
        if tool_calls:
            parts += extract_tool_calls(tool_calls)
        content = get_property_value(message, "content")
        if _is_text_part(content):
            parts.append(Text(content=str(content)))

        output_messages.append(
            OutputMessage(
                finish_reason=map_finish_reason(
                    get_property_value(choice, "finish_reason")
                ),
                role=get_property_value(message, "role") or "assistant",
                parts=parts,
            )
        )
    return output_messages


def create_chat_invocation(
    handler: TelemetryHandler,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    capture_content: bool,
) -> InferenceInvocation:
    invocation = handler.start_inference(
        resolve_provider_from_kwargs(kwargs, args),
        request_model=get_model(args, kwargs),
    )
    invocation.temperature = kwargs.get("temperature")
    invocation.top_p = kwargs.get("top_p")
    invocation.max_tokens = kwargs.get("max_tokens")
    invocation.presence_penalty = kwargs.get("presence_penalty")
    invocation.frequency_penalty = kwargs.get("frequency_penalty")
    invocation.seed = kwargs.get("seed")

    if (stop_sequences := kwargs.get("stop")) is not None:
        if isinstance(stop_sequences, str):
            stop_sequences = [stop_sequences]
        invocation.stop_sequences = stop_sequences

    if (choice_count := kwargs.get("n")) is not None:
        if isinstance(choice_count, int) and choice_count != 1:
            invocation.attributes[
                GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT
            ] = choice_count

    if capture_content:  # optimization
        invocation.input_messages = prepare_input_messages(
            _get_messages(args, kwargs)
        )
        invocation.tool_definitions = prepare_tool_definitions(
            kwargs.get("tools")
        )
    return invocation


def create_embedding_invocation(
    handler: TelemetryHandler,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> EmbeddingInvocation:
    encoding_format = kwargs.get("encoding_format")
    invocation = handler.start_embedding(
        resolve_provider_from_kwargs(kwargs, args),
        request_model=get_model(args, kwargs),
    )
    if encoding_format is not None:
        if isinstance(encoding_format, str):
            encoding_format = [encoding_format]
        invocation.encoding_formats = encoding_format
    if (dimensions := kwargs.get("dimensions")) is not None:
        invocation.dimension_count = dimensions
    return invocation


def set_chat_response(
    invocation: InferenceInvocation,
    response: Any,
    capture_content: bool,
) -> None:
    provider = resolve_provider_from_response(response)
    if provider:
        invocation.provider = provider

    if get_property_value(response, "model"):
        invocation.response_model_name = get_property_value(response, "model")

    if get_property_value(response, "id"):
        invocation.response_id = get_property_value(response, "id")

    choices = get_property_value(response, "choices")
    if choices:
        invocation.finish_reasons = [
            map_finish_reason(get_property_value(choice, "finish_reason"))
            for choice in choices
        ]
        if capture_content:  # optimization
            invocation.output_messages = prepare_output_messages(choices)

    usage = get_property_value(response, "usage")
    if usage:
        invocation.input_tokens = get_property_value(usage, "prompt_tokens")
        invocation.output_tokens = get_property_value(
            usage, "completion_tokens"
        )
        prompt_details = get_property_value(usage, "prompt_tokens_details")
        if prompt_details:
            cached = get_property_value(prompt_details, "cached_tokens")
            if cached is not None:
                invocation.cache_read_input_tokens = cached


def set_embedding_response(
    invocation: EmbeddingInvocation,
    response: Any,
) -> None:
    provider = resolve_provider_from_response(response)
    if provider:
        invocation.provider = provider

    if get_property_value(response, "model"):
        invocation.response_model_name = get_property_value(response, "model")

    usage = get_property_value(response, "usage")
    if usage:
        invocation.input_tokens = get_property_value(usage, "prompt_tokens")


def handle_span_exception(span: Any, error: BaseException) -> None:
    from opentelemetry.semconv.attributes import (  # noqa: PLC0415
        error_attributes as ErrorAttributes,
    )

    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()


__all__ = [
    "_CHAT",
    "_EMBEDDINGS",
    "_LITELLM_PROVIDER",
    "create_chat_invocation",
    "create_embedding_invocation",
    "get_model",
    "handle_span_exception",
    "is_streaming",
    "map_finish_reason",
    "prepare_input_messages",
    "prepare_output_messages",
    "prepare_tool_definitions",
    "resolve_provider_from_kwargs",
    "resolve_provider_from_response",
    "set_chat_response",
    "set_embedding_response",
]
