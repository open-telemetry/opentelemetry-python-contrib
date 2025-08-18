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

import time
from threading import Lock
from typing import List, Optional
from uuid import UUID

from opentelemetry._events import get_event_logger
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .data import ChatGeneration, Error, Message
from .emitters import SpanMetricEmitter, SpanMetricEventEmitter
from .types import LLMInvocation

# TODO: Get the tool version for emitting spans, use GenAI Utils for now
from .version import __version__


class TelemetryClient:
    """
    High-level client managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(self, emitter_type_full: bool = True, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        event_logger_provider = kwargs.get("event_logger_provider")
        self._event_logger = get_event_logger(
            __name__,
            __version__,
            event_logger_provider=event_logger_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        self._emitter = (
            SpanMetricEventEmitter(
                tracer=self._tracer,
                meter=self._meter,
                event_logger=self._event_logger,
            )
            if emitter_type_full
            else SpanMetricEmitter(tracer=self._tracer, meter=self._meter)
        )

        self._llm_registry: dict[UUID, LLMInvocation] = {}
        self._lock = Lock()

    def start_llm(
        self,
        prompts: List[Message],
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **attributes,
    ):
        invocation = LLMInvocation(
            messages=prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )
        with self._lock:
            self._llm_registry[invocation.run_id] = invocation
        self._emitter.init(invocation)

    def stop_llm(
        self,
        run_id: UUID,
        chat_generations: List[ChatGeneration],
        **attributes,
    ) -> LLMInvocation:
        with self._lock:
            invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.chat_generations = chat_generations
        invocation.attributes.update(attributes)
        self._emitter.emit(invocation)
        return invocation

    def fail_llm(
        self, run_id: UUID, error: Error, **attributes
    ) -> LLMInvocation:
        with self._lock:
            invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.attributes.update(**attributes)
        self._emitter.error(error, invocation)
        return invocation


# Singleton accessor
_default_client: TelemetryClient | None = None


def get_telemetry_client(
    emitter_type_full: bool = True, **kwargs
) -> TelemetryClient:
    global _default_client
    if _default_client is None:
        _default_client = TelemetryClient(
            emitter_type_full=emitter_type_full, **kwargs
        )
    return _default_client


# Module‐level convenience functions
def llm_start(
    prompts: List[Message],
    run_id: UUID,
    parent_run_id: Optional[UUID] = None,
    **attributes,
):
    return get_telemetry_client().start_llm(
        prompts=prompts,
        run_id=run_id,
        parent_run_id=parent_run_id,
        **attributes,
    )


def llm_stop(
    run_id: UUID, chat_generations: List[ChatGeneration], **attributes
) -> LLMInvocation:
    return get_telemetry_client().stop_llm(
        run_id=run_id, chat_generations=chat_generations, **attributes
    )


def llm_fail(run_id: UUID, error: Error, **attributes) -> LLMInvocation:
    return get_telemetry_client().fail_llm(
        run_id=run_id, error=error, **attributes
    )
