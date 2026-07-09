# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, List

from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
)

# There is no ``GenAiProviderNameValues`` enum member for HuggingFace or a
# generic local inference backend. A local ``transformers`` pipeline runs the
# model in-process (no network, no hosted provider), so the ``huggingface``
# literal is used for ``gen_ai.provider.name``.
_HUGGINGFACE_PROVIDER = "huggingface"

# The ``transformers`` local pipeline exposes no finish reason for a generated
# sequence, so output messages carry a ``None`` finish reason.
_UNSET_FINISH_REASON: str | None = None


def get_request_model(instance: Any) -> str | None:
    """Read the request model name from a ``TextGenerationPipeline`` instance.

    ``transformers`` pipelines expose the loaded model via ``instance.model``.
    The model name is available as ``model.name_or_path`` and, as a fallback,
    ``model.config._name_or_path``. A safe getattr chain is used because the
    fake/partial instances used in tests (and some model configs) may not
    populate every attribute.
    """
    model = getattr(instance, "model", None)
    if model is None:
        return None

    name_or_path = getattr(model, "name_or_path", None)
    if isinstance(name_or_path, str) and name_or_path:
        return name_or_path

    config = getattr(model, "config", None)
    if config is not None:
        config_name = getattr(config, "_name_or_path", None)
        if isinstance(config_name, str) and config_name:
            return config_name

    return None


def _prompt_to_texts(prompt: Any) -> List[str]:
    """Normalize the first positional argument of ``__call__`` into text(s).

    ``TextGenerationPipeline.__call__`` accepts a single prompt string or a
    list of prompt strings (batched). Non-string entries are stringified so
    content capture never raises.
    """
    if prompt is None:
        return []
    if isinstance(prompt, str):
        return [prompt]
    if isinstance(prompt, (list, tuple)):
        return [
            item if isinstance(item, str) else str(item) for item in prompt
        ]
    return [str(prompt)]


def prepare_input_messages(prompt: Any) -> List[InputMessage]:
    """Build ``InputMessage`` objects from the pipeline prompt argument."""
    return [
        InputMessage(role="user", parts=[Text(content=text)])
        for text in _prompt_to_texts(prompt)
    ]


def _generated_text(entry: Any) -> str | None:
    """Extract the ``generated_text`` value from a single pipeline result."""
    if isinstance(entry, dict):
        text = entry.get("generated_text")
    else:
        text = getattr(entry, "generated_text", None)
    if isinstance(text, str):
        return text
    if text is not None:
        return str(text)
    return None


def prepare_output_messages(result: Any) -> List[OutputMessage]:
    """Build ``OutputMessage`` objects from a pipeline return value.

    ``TextGenerationPipeline.__call__`` returns a list of dicts such as
    ``[{"generated_text": "..."}]``. When a batch of prompts is passed it
    returns a list of such lists. Both shapes are flattened here. A local
    pipeline exposes no finish reason, so ``finish_reason`` is left unset.
    """
    if result is None:
        return []

    entries: list[Any]
    if isinstance(result, (list, tuple)):
        entries = list(result)
    else:
        entries = [result]

    output_messages: list[OutputMessage] = []
    for entry in entries:
        # Batched pipelines return a list of lists.
        if isinstance(entry, (list, tuple)):
            for sub_entry in entry:
                text = _generated_text(sub_entry)
                if text is not None:
                    output_messages.append(_text_output_message(text))
            continue
        text = _generated_text(entry)
        if text is not None:
            output_messages.append(_text_output_message(text))
    return output_messages


def _text_output_message(text: str) -> OutputMessage:
    return OutputMessage(
        role="assistant",
        parts=[Text(content=text)],
        finish_reason=_UNSET_FINISH_REASON,
    )


__all__ = [
    "_HUGGINGFACE_PROVIDER",
    "get_request_model",
    "prepare_input_messages",
    "prepare_output_messages",
]
