# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

from .utils import (
    _HUGGINGFACE_PROVIDER,
    get_request_model,
    prepare_input_messages,
    prepare_output_messages,
)


def text_generation(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``transformers.TextGenerationPipeline.__call__``.

    ``TextGenerationPipeline`` runs a HuggingFace model locally (in-process
    inference). The first positional argument to ``__call__`` is the prompt
    (a string or a list of strings) and the return value is a list of dicts
    such as ``[{"generated_text": "..."}]``. Local inference exposes no token
    usage and no finish reason, so those fields are intentionally omitted.
    """
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_inference(
            _HUGGINGFACE_PROVIDER,
            request_model=get_request_model(instance),
        )
        if capture_content:  # optimization
            prompt = args[0] if args else kwargs.get("text_inputs")
            invocation.input_messages = prepare_input_messages(prompt)

        try:
            result = wrapped(*args, **kwargs)
            if capture_content:  # optimization
                invocation.output_messages = prepare_output_messages(result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = ["text_generation"]
