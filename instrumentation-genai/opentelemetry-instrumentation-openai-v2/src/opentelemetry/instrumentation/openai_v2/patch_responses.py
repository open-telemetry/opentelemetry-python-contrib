# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

from .response_extractors import (
    apply_request_attributes,
    extract_params,
    get_inference_creation_kwargs,
    set_invocation_response_attributes,
)
from .response_wrappers import ResponseStreamWrapper
from .utils import is_streaming


def responses_create(handler: TelemetryHandler):
    """Wrap the `create` method of the `Responses` class to trace it."""

    capture_content = handler.should_capture_content()

    def traced_method(wrapped, instance, args, kwargs):
        params = extract_params(**kwargs)
        invocation = handler.start_inference(
            **get_inference_creation_kwargs(params, instance)
        )
        apply_request_attributes(invocation, params, capture_content)

        try:
            result = wrapped(*args, **kwargs)
            parsed_result = _get_response_stream_result(result)

            if is_streaming(kwargs):
                return ResponseStreamWrapper(
                    parsed_result,
                    invocation,
                    capture_content,
                )

            set_invocation_response_attributes(
                invocation, parsed_result, capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def _get_response_stream_result(result):
    if hasattr(result, "parse"):
        return result.parse()
    return result
