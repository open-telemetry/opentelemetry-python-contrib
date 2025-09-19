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

"""
Telemetry handler for GenAI invocations.

This module exposes the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data (spans and related attributes).
It supports starting, stopping, and failing LLM invocations.

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage:
    handler = get_telemetry_handler()
    handler.start_llm(input_messages, request_model, **attrs)
    handler.stop_llm(invocation, output_messages, **attrs)
    handler.fail_llm(invocation, error, **attrs)
"""

import time
from typing import Any, List, Optional

from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .generators import SpanGenerator
from .types import Error, InputMessage, LLMInvocation, OutputMessage
from .version import __version__


def _apply_known_attrs_to_invocation(
    invocation: LLMInvocation, attributes: dict[str, Any]
) -> None:
    """Pop known fields from attributes and set them on the invocation.

    Mutates the provided attributes dict by popping known keys, leaving
    only unknown/custom attributes behind for the caller to persist into
    invocation.attributes.
    """
    if "provider" in attributes:
        invocation.provider = attributes.pop("provider")
    if "response_model_name" in attributes:
        invocation.response_model_name = attributes.pop("response_model_name")
    if "response_id" in attributes:
        invocation.response_id = attributes.pop("response_id")
    if "input_tokens" in attributes:
        invocation.input_tokens = attributes.pop("input_tokens")
    if "output_tokens" in attributes:
        invocation.output_tokens = attributes.pop("output_tokens")


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(self, **kwargs: Any):
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )

        self._generator = SpanGenerator(tracer=self._tracer)

    def start_llm(
        self,
        request_model: str,
        input_messages: List[InputMessage],
        **attributes: Any,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry.

        Known attributes provided via ``**attributes`` (``provider``,
        ``response_model_name``, ``response_id``, ``input_tokens``,
        ``output_tokens``) are extracted and set as explicit fields on the
        ``LLMInvocation``. Any remaining keys are preserved in
        ``invocation.attributes`` for custom metadata.

        Returns the ``LLMInvocation`` to use with `stop_llm` and `fail_llm`.
        """
        invocation = LLMInvocation(
            request_model=request_model,
            input_messages=input_messages,
            attributes=attributes,
        )
        _apply_known_attrs_to_invocation(invocation, invocation.attributes)
        self._generator.start(invocation)
        return invocation

    def stop_llm(
        self,
        invocation: LLMInvocation,
        output_messages: List[OutputMessage],
        **attributes: Any,
    ) -> LLMInvocation:
        """Finalize an LLM invocation successfully and end its span."""
        invocation.end_time = time.time()
        invocation.output_messages = output_messages
        _apply_known_attrs_to_invocation(invocation, attributes)
        invocation.attributes.update(attributes)
        self._generator.finish(invocation)
        return invocation

    def fail_llm(
        self, invocation: LLMInvocation, error: Error, **attributes: Any
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status."""
        invocation.end_time = time.time()
        _apply_known_attrs_to_invocation(invocation, attributes)
        invocation.attributes.update(**attributes)
        self._generator.error(error, invocation)
        return invocation


def get_telemetry_handler(**kwargs: Any) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: Optional[TelemetryHandler] = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(**kwargs)
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
