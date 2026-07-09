# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import json
from typing import Any, Callable, Mapping

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import Error

from .utils import (
    _AWS_BEDROCK_PROVIDER,
    apply_anthropic_invoke_request,
    apply_anthropic_invoke_response,
    apply_converse_request,
    apply_converse_response,
)


def converse_wrapper(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the bedrock-runtime ``converse`` method."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        model_id = kwargs.get("modelId")
        invocation = handler.start_inference(
            _AWS_BEDROCK_PROVIDER,
            request_model=model_id,
        )
        _safe_apply(
            apply_converse_request, invocation, kwargs, capture_content
        )

        try:
            response = wrapped(*args, **kwargs)
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

        # ``converse`` has no distinct response model; mirror the request model.
        invocation.response_model_name = model_id
        if isinstance(response, Mapping):
            _safe_apply(
                apply_converse_response,
                invocation,
                response,
                capture_content,
            )
        invocation.stop()
        return response

    return traced_method


def invoke_model_wrapper(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the bedrock-runtime ``invoke_model`` method.

    Only the Anthropic Messages body shape is parsed. Unrecognized bodies still
    emit a span with the request model and operation name; token/content
    parsing is skipped. All body parsing is defensive and never raises.
    """
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        model_id = kwargs.get("modelId")
        invocation = handler.start_inference(
            _AWS_BEDROCK_PROVIDER,
            request_model=model_id,
        )

        request_body = _safe_load_json(kwargs.get("body"))
        if isinstance(request_body, Mapping):
            _safe_apply(
                apply_anthropic_invoke_request,
                invocation,
                request_body,
                capture_content,
            )

        try:
            response = wrapped(*args, **kwargs)
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

        invocation.response_model_name = model_id
        _handle_invoke_response(invocation, response, capture_content)
        invocation.stop()
        return response

    return traced_method


def _handle_invoke_response(
    invocation: InferenceInvocation,
    response: Any,
    capture_content: bool,
) -> None:
    """Read and re-buffer the ``invoke_model`` response body defensively.

    The response ``body`` is a ``StreamingBody`` that can only be read once, so
    it is replaced with a fresh in-memory stream after parsing to keep the
    caller's ``response["body"].read()`` working.
    """
    if not isinstance(response, Mapping):
        return
    body = response.get("body")
    read = getattr(body, "read", None)
    if not callable(read):
        return
    try:
        raw = read()
    except Exception:  # never fail instrumentation on a bad body
        return

    if isinstance(raw, (bytes, bytearray)):
        response["body"] = _rebuffer_streaming_body(bytes(raw))

    parsed = _safe_load_json(raw)
    if isinstance(parsed, Mapping):
        _safe_apply(
            apply_anthropic_invoke_response,
            invocation,
            parsed,
            capture_content,
        )


def _rebuffer_streaming_body(raw: bytes) -> Any:
    """Return a re-readable body equivalent to the consumed StreamingBody."""
    try:
        from botocore.response import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            StreamingBody,
        )

        return StreamingBody(io.BytesIO(raw), len(raw))
    except Exception:  # pragma: no cover - defensive fallback
        return io.BytesIO(raw)


def _safe_load_json(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return json.loads(value)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def _safe_apply(
    fn: Callable[..., None],
    invocation: InferenceInvocation,
    payload: Mapping[str, Any],
    capture_content: bool,
) -> None:
    """Run a request/response mapping helper without ever raising.

    Body parsing is best-effort telemetry; a malformed payload must not break
    the wrapped Bedrock call.
    """
    try:
        fn(invocation, payload, capture_content)
    except Exception:  # noqa: BLE001 - telemetry must not raise
        pass


__all__ = [
    "converse_wrapper",
    "invoke_model_wrapper",
]
