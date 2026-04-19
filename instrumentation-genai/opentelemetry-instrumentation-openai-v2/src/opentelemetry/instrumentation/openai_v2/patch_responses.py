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

from typing import Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import ContentCapturingMode, Error

from .instruments import Instruments
from .response_extractors import (
    _apply_request_attributes,
    _get_inference_creation_kwargs,
    _set_invocation_response_attributes,
)
from .response_wrappers import ResponseStreamWrapper
from .utils import is_streaming


def responses_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap the `create` method of the `Responses` class to trace it."""

    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_inference(
            **_get_inference_creation_kwargs(kwargs, instance)
        )
        _apply_request_attributes(invocation, kwargs, capture_content)

        try:
            result = wrapped(*args, **kwargs)
            parsed_result = _get_response_stream_result(result)

            if is_streaming(kwargs):
                return ResponseStreamWrapper(
                    parsed_result,
                    invocation,
                    capture_content,
                )

            _set_invocation_response_attributes(
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
