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
    handler.start_llm(prompts, run_id, **attrs)
    handler.stop_llm(run_id, chat_generations, **attrs)
    handler.fail_llm(run_id, error, **attrs)
"""

import time
from typing import Any, List, Optional
from uuid import UUID

from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .generators import SpanGenerator
from .types import Error, InputMessage, LLMInvocation, OutputMessage
from .version import __version__


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(self, emitter_type_full: bool = True, **kwargs: Any):
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )

        # TODO: trigger span+metric+event generation based on the full emitter flag
        self._generator = SpanGenerator(tracer=self._tracer)

        self._llm_registry: dict[UUID, LLMInvocation] = {}

    def start_llm(
        self,
        request_model: str,
        prompts: List[InputMessage],
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **attributes: Any,
    ) -> None:
        invocation = LLMInvocation(
            request_model=request_model,
            messages=prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )
        self._llm_registry[invocation.run_id] = invocation
        self._generator.start(invocation)

    def stop_llm(
        self,
        run_id: UUID,
        chat_generations: List[OutputMessage],
        **attributes: Any,
    ) -> LLMInvocation:
        invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.chat_generations = chat_generations
        invocation.attributes.update(attributes)
        self._generator.finish(invocation)
        return invocation

    def fail_llm(
        self, run_id: UUID, error: Error, **attributes: Any
    ) -> LLMInvocation:
        invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.attributes.update(**attributes)
        self._generator.error(error, invocation)
        return invocation


def get_telemetry_handler(
    emitter_type_full: bool = True, **kwargs: Any
) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: Optional[TelemetryHandler] = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(
            emitter_type_full=emitter_type_full, **kwargs
        )
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
