# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Iterable, List, Mapping

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
)

# ``ibm.watsonx.ai`` is a well-known value in ``GenAiProviderNameValues`` in the
# semconv package, so the generated enum member is used instead of a raw string
# literal.
_WATSONX_PROVIDER = (
    GenAIAttributes.GenAiProviderNameValues.IBM_WATSONX_AI.value
)

_TEXT_COMPLETION = (
    GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
)
_CHAT = GenAIAttributes.GenAiOperationNameValues.CHAT.value


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _request_model(instance: Any) -> str:
    """Read the request model from a ``ModelInference`` instance.

    The instance carries a ``model_id`` string attribute.
    """
    return getattr(instance, "model_id", None) or ""


def _generate_params(kwargs: Mapping[str, Any]) -> Mapping[str, Any]:
    params = kwargs.get("params")
    if isinstance(params, Mapping):
        return params
    return {}


def _apply_request_params(
    invocation: InferenceInvocation,
    kwargs: Mapping[str, Any],
) -> None:
    """Best-effort mapping of watsonx text-generation params to invocation
    request attributes.

    watsonx accepts ``params`` either as a plain ``dict`` (using the
    ``GenTextParamsMetaNames`` keys such as ``temperature``, ``top_p``,
    ``max_new_tokens``, ``random_seed``, ``stop_sequences``) or as a typed
    parameters object. Only plain-``dict`` params are mapped here; typed
    objects are left untouched.
    """
    params = _generate_params(kwargs)
    if not params:
        return

    temperature = params.get("temperature")
    if isinstance(temperature, (int, float)):
        invocation.temperature = float(temperature)

    top_p = params.get("top_p")
    if isinstance(top_p, (int, float)):
        invocation.top_p = float(top_p)

    max_new_tokens = params.get("max_new_tokens")
    if isinstance(max_new_tokens, int):
        invocation.max_tokens = max_new_tokens

    random_seed = params.get("random_seed")
    if isinstance(random_seed, int):
        invocation.seed = random_seed

    stop_sequences = params.get("stop_sequences")
    if isinstance(stop_sequences, str):
        invocation.stop_sequences = [stop_sequences]
    elif isinstance(stop_sequences, Iterable):
        invocation.stop_sequences = [str(seq) for seq in stop_sequences]


def _text_from_message_content(content: Any) -> str | None:
    """A watsonx chat message ``content`` may be a plain string or a list of
    content blocks (each block a dict with a ``text`` field). Return the text
    representation when available."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        texts: list[str] = []
        for part in content:
            text = _get(part, "text")
            if isinstance(text, str):
                texts.append(text)
        if texts:
            return "".join(texts)
    return None


def _prepare_prompt_input_messages(
    prompt: Any,
) -> List[InputMessage]:
    """``generate`` / ``generate_text_stream`` take a plain string prompt (or a
    list of strings for batch)."""
    messages: list[InputMessage] = []
    if isinstance(prompt, str):
        prompts: list[str] = [prompt]
    elif isinstance(prompt, Iterable):
        prompts = [str(item) for item in prompt]
    else:
        return messages
    for text in prompts:
        messages.append(InputMessage(role="user", parts=[Text(content=text)]))
    return messages


def _prepare_chat_input_messages(
    messages: Iterable[Any],
) -> List[InputMessage]:
    chat_messages: list[InputMessage] = []
    for message in messages:
        role = _get(message, "role")
        parts: list[Any] = []
        text = _text_from_message_content(_get(message, "content"))
        if text is not None:
            parts.append(Text(content=text))
        chat_messages.append(
            InputMessage(
                role=str(role) if role is not None else "user", parts=parts
            )
        )
    return chat_messages


def create_text_generation_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    args: tuple[Any, ...],
    instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    invocation = handler.start_inference(
        _WATSONX_PROVIDER,
        request_model=_request_model(instance),
        operation_name=_TEXT_COMPLETION,
    )
    _apply_request_params(invocation, kwargs)
    if capture_content:  # optimization
        prompt = kwargs.get("prompt")
        if prompt is None and args:
            prompt = args[0]
        invocation.input_messages = _prepare_prompt_input_messages(prompt)
    return invocation


def create_chat_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    args: tuple[Any, ...],
    instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    invocation = handler.start_inference(
        _WATSONX_PROVIDER,
        request_model=_request_model(instance),
        operation_name=_CHAT,
    )
    _apply_request_params(invocation, kwargs)
    if capture_content:  # optimization
        messages = kwargs.get("messages")
        if messages is None and args:
            messages = args[0]
        invocation.input_messages = _prepare_chat_input_messages(
            messages or []
        )
    return invocation


def _first_result(response: Any) -> Any:
    """``generate`` returns a single dict, or a list of dicts for batch prompts.
    Return the primary result dict."""
    if isinstance(response, list):
        return response[0] if response else None
    return response


def set_text_generation_response(
    invocation: InferenceInvocation,
    response: Any,
    capture_content: bool,
) -> None:
    primary = _first_result(response)
    if primary is None:
        return

    model_id = _get(primary, "model_id")
    if model_id:
        invocation.response_model_name = str(model_id)

    results = _get(primary, "results")
    if not results:
        return

    finish_reasons: list[str] = []
    output_messages: list[OutputMessage] = []
    total_input_tokens = 0
    total_output_tokens = 0
    has_input_tokens = False
    has_output_tokens = False

    for result in results:
        stop_reason = _get(result, "stop_reason")
        finish_reason = (
            str(stop_reason) if stop_reason is not None else "error"
        )
        finish_reasons.append(finish_reason)

        input_token_count = _get(result, "input_token_count")
        if isinstance(input_token_count, int):
            total_input_tokens += input_token_count
            has_input_tokens = True

        output_token_count = _get(result, "generated_token_count")
        if isinstance(output_token_count, int):
            total_output_tokens += output_token_count
            has_output_tokens = True

        if capture_content:  # optimization
            generated_text = _get(result, "generated_text")
            parts: list[Any] = []
            if isinstance(generated_text, str):
                parts.append(Text(content=generated_text))
            output_messages.append(
                OutputMessage(
                    role="assistant",
                    finish_reason=finish_reason,
                    parts=parts,
                )
            )

    if finish_reasons:
        invocation.finish_reasons = finish_reasons
    if has_input_tokens:
        invocation.input_tokens = total_input_tokens
    if has_output_tokens:
        invocation.output_tokens = total_output_tokens
    if capture_content and output_messages:  # optimization
        invocation.output_messages = output_messages


def set_chat_response(
    invocation: InferenceInvocation,
    response: Any,
    capture_content: bool,
) -> None:
    if response is None:
        return

    model_id = _get(response, "model_id")
    if model_id:
        invocation.response_model_name = str(model_id)

    response_id = _get(response, "id")
    if response_id:
        invocation.response_id = str(response_id)

    usage = _get(response, "usage")
    if usage is not None:
        prompt_tokens = _get(usage, "prompt_tokens")
        if isinstance(prompt_tokens, int):
            invocation.input_tokens = prompt_tokens
        completion_tokens = _get(usage, "completion_tokens")
        if isinstance(completion_tokens, int):
            invocation.output_tokens = completion_tokens

    choices = _get(response, "choices")
    if not choices:
        return

    finish_reasons: list[str] = []
    output_messages: list[OutputMessage] = []
    for choice in choices:
        finish_reason_value = _get(choice, "finish_reason")
        finish_reason = (
            str(finish_reason_value)
            if finish_reason_value is not None
            else "error"
        )
        finish_reasons.append(finish_reason)

        if capture_content:  # optimization
            message = _get(choice, "message")
            parts: list[Any] = []
            if message is not None:
                text = _text_from_message_content(_get(message, "content"))
                if text is not None:
                    parts.append(Text(content=text))
            role = _get(message, "role") if message is not None else None
            output_messages.append(
                OutputMessage(
                    role=str(role) if role is not None else "assistant",
                    finish_reason=finish_reason,
                    parts=parts,
                )
            )

    if finish_reasons:
        invocation.finish_reasons = finish_reasons
    if capture_content and output_messages:  # optimization
        invocation.output_messages = output_messages


__all__ = [
    "_CHAT",
    "_TEXT_COMPLETION",
    "_WATSONX_PROVIDER",
    "create_chat_invocation",
    "create_text_generation_invocation",
    "set_chat_response",
    "set_text_generation_response",
]
