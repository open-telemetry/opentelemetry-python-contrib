# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Iterable, Mapping

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
)

# ``aws.bedrock`` is a well-known value in ``GenAiProviderNameValues`` in the
# semconv package, so the generated enum member is used instead of a raw string
# literal.
_AWS_BEDROCK_PROVIDER = (
    GenAIAttributes.GenAiProviderNameValues.AWS_BEDROCK.value
)


def _text_from_content_blocks(content: Any) -> str | None:
    """Concatenate the ``text`` fields of a Bedrock content-block list.

    Bedrock ``converse`` messages carry content as a list of blocks such as
    ``[{"text": "..."}]``. Anthropic ``invoke_model`` responses use the same
    shape. Non-text blocks (``toolUse``, ``image``, ...) are ignored.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        texts: list[str] = []
        for block in content:
            if isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
        if texts:
            return "".join(texts)
    return None


def _prepare_input_messages(messages: Any) -> list[InputMessage]:
    """Map Bedrock ``converse`` / Anthropic request messages to InputMessages.

    Best-effort: unknown shapes are skipped rather than raising.
    """
    input_messages: list[InputMessage] = []
    if not isinstance(messages, Iterable):
        return input_messages
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        role = message.get("role")
        text = _text_from_content_blocks(message.get("content"))
        parts: list[Any] = []
        if text is not None:
            parts.append(Text(content=text))
        input_messages.append(InputMessage(role=str(role), parts=parts))
    return input_messages


def apply_converse_request(
    invocation: InferenceInvocation,
    kwargs: Mapping[str, Any],
    capture_content: bool,
) -> None:
    """Populate request-side attributes from ``converse`` kwargs.

    ``inferenceConfig`` carries the sampling parameters (``maxTokens``,
    ``temperature``, ``topP``, ``stopSequences``).
    """
    inference_config = kwargs.get("inferenceConfig")
    if isinstance(inference_config, Mapping):
        max_tokens = inference_config.get("maxTokens")
        if isinstance(max_tokens, int):
            invocation.max_tokens = max_tokens
        temperature = inference_config.get("temperature")
        if isinstance(temperature, (int, float)):
            invocation.temperature = float(temperature)
        top_p = inference_config.get("topP")
        if isinstance(top_p, (int, float)):
            invocation.top_p = float(top_p)
        stop_sequences = inference_config.get("stopSequences")
        if isinstance(stop_sequences, list):
            invocation.stop_sequences = [str(s) for s in stop_sequences]

    if capture_content:
        invocation.input_messages = _prepare_input_messages(
            kwargs.get("messages")
        )


def apply_converse_response(
    invocation: InferenceInvocation,
    response: Mapping[str, Any],
    capture_content: bool,
) -> None:
    """Populate response-side attributes from a ``converse`` response.

    The ``converse`` API does not return a distinct response model, so
    ``response_model_name`` is left to mirror the request model when set by the
    caller.
    """
    stop_reason = response.get("stopReason")
    if stop_reason is not None:
        invocation.finish_reasons = [str(stop_reason)]

    usage = response.get("usage")
    if isinstance(usage, Mapping):
        input_tokens = usage.get("inputTokens")
        if isinstance(input_tokens, int):
            invocation.input_tokens = input_tokens
        output_tokens = usage.get("outputTokens")
        if isinstance(output_tokens, int):
            invocation.output_tokens = output_tokens

    output = response.get("output")
    message = output.get("message") if isinstance(output, Mapping) else None
    if isinstance(message, Mapping):
        role = message.get("role") or "assistant"
        parts: list[Any] = []
        if capture_content:
            text = _text_from_content_blocks(message.get("content"))
            if text is not None:
                parts.append(Text(content=text))
        invocation.output_messages = [
            OutputMessage(
                role=str(role),
                parts=parts,
                finish_reason=str(stop_reason) if stop_reason else "",
            )
        ]


def apply_anthropic_invoke_request(
    invocation: InferenceInvocation,
    body: Mapping[str, Any],
    capture_content: bool,
) -> None:
    """Populate request attributes from an Anthropic ``invoke_model`` body."""
    max_tokens = body.get("max_tokens")
    if isinstance(max_tokens, int):
        invocation.max_tokens = max_tokens
    temperature = body.get("temperature")
    if isinstance(temperature, (int, float)):
        invocation.temperature = float(temperature)
    top_p = body.get("top_p")
    if isinstance(top_p, (int, float)):
        invocation.top_p = float(top_p)
    stop_sequences = body.get("stop_sequences")
    if isinstance(stop_sequences, list):
        invocation.stop_sequences = [str(s) for s in stop_sequences]

    if capture_content:
        invocation.input_messages = _prepare_input_messages(
            body.get("messages")
        )


def apply_anthropic_invoke_response(
    invocation: InferenceInvocation,
    body: Mapping[str, Any],
    capture_content: bool,
) -> None:
    """Populate response attributes from an Anthropic ``invoke_model`` body."""
    stop_reason = body.get("stop_reason")
    if stop_reason is not None:
        invocation.finish_reasons = [str(stop_reason)]

    usage = body.get("usage")
    if isinstance(usage, Mapping):
        input_tokens = usage.get("input_tokens")
        if isinstance(input_tokens, int):
            invocation.input_tokens = input_tokens
        output_tokens = usage.get("output_tokens")
        if isinstance(output_tokens, int):
            invocation.output_tokens = output_tokens

    role = body.get("role") or "assistant"
    parts: list[Any] = []
    if capture_content:
        text = _text_from_content_blocks(body.get("content"))
        if text is not None:
            parts.append(Text(content=text))
    invocation.output_messages = [
        OutputMessage(
            role=str(role),
            parts=parts,
            finish_reason=str(stop_reason) if stop_reason else "",
        )
    ]


__all__ = [
    "_AWS_BEDROCK_PROVIDER",
    "apply_anthropic_invoke_request",
    "apply_anthropic_invoke_response",
    "apply_converse_request",
    "apply_converse_response",
]
