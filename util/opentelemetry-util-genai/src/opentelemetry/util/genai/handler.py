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

This module provides the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data as spans, metrics, and events.
It supports starting, stopping, and failing LLM invocations,
and provides module-level convenience functions for these operations.

Classes:
    TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    get_telemetry_handler: Returns a singleton TelemetryHandler instance.
    llm_start: Starts a new LLM invocation.
    llm_stop: Stops an LLM invocation and emits telemetry.
    llm_fail: Marks an LLM invocation as failed and emits error telemetry.

Usage:
    Use the module-level functions (`llm_start`, `llm_stop`, `llm_fail`) to
    instrument GenAI invocations for telemetry collection.
"""

import time
from threading import Lock
from typing import Any, List, Optional
from uuid import UUID

from opentelemetry._events import get_event_logger
from opentelemetry._logs import get_logger
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .generators import SpanMetricGenerator
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

        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url=Schemas.V1_36_0.value,
        )

        event_logger_provider = kwargs.get("event_logger_provider")
        self._event_logger = get_event_logger(
            __name__,
            __version__,
            event_logger_provider=event_logger_provider,
            schema_url=Schemas.V1_36_0.value,
        )

        logger_provider = kwargs.get("logger_provider")
        self._logger = get_logger(
            __name__,
            __version__,
            logger_provider=logger_provider,
            schema_url=Schemas.V1_36_0.value,
        )

        # TODO: trigger span+metric+event generation based on the content capturing mode
        self._generator = SpanMetricGenerator(
            tracer=self._tracer,
            meter=self._meter,
            capture_content=self._should_collect_content(),
        )

        self._llm_registry: dict[UUID, LLMInvocation] = {}
        self._lock = Lock()

    @staticmethod
    def _should_collect_content() -> bool:
        # TODO: Get the content capturing mode from the environment variable
        # from .utils import get_content_capturing_mode
        # from opentelemetry.instrumentation._semconv import (
        #     OTEL_SEMCONV_STABILITY_OPT_IN,
        #     _OpenTelemetrySemanticConventionStability,
        # )
        return True  # Placeholder for future config

    def start_llm(
        self,
        prompts: List[InputMessage],
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **attributes: Any,
    ) -> None:
        invocation = LLMInvocation(
            messages=prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )
        with self._lock:
            self._llm_registry[invocation.run_id] = invocation
        self._generator.start(invocation)

    def stop_llm(
        self,
        run_id: UUID,
        chat_generations: List[OutputMessage],
        **attributes: Any,
    ) -> LLMInvocation:
        with self._lock:
            invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.chat_generations = chat_generations
        invocation.attributes.update(attributes)
        self._generator.finish(invocation)
        return invocation

    def fail_llm(
        self, run_id: UUID, error: Error, **attributes: Any
    ) -> LLMInvocation:
        with self._lock:
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
