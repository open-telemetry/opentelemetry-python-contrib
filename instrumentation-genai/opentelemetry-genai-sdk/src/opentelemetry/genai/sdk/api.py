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

from .types import LLMInvocation, ToolInvocation
from .exporters import SpanMetricEventExporter, SpanMetricExporter
from .data import Message, ChatGeneration, Error, ToolOutput, ToolFunction

from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.metrics import get_meter
from opentelemetry.trace import get_tracer
from opentelemetry._events import get_event_logger
from opentelemetry.semconv.schemas import Schemas


class TelemetryClient:
    """
    High-level client managing GenAI invocation lifecycles and exporting
    them as spans, metrics, and events.
    """
    def __init__(self, exporter_type_full: bool = True, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        self._tracer = get_tracer(
            __name__, __version__, tracer_provider, schema_url=Schemas.V1_28_0.value
        )

        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__, __version__, meter_provider, schema_url=Schemas.V1_28_0.value
        )

        event_logger_provider = kwargs.get("event_logger_provider")
        self._event_logger = get_event_logger(
            __name__, __version__, event_logger_provider=event_logger_provider, schema_url=Schemas.V1_28_0.value
        )

        self._exporter = (
            SpanMetricEventExporter(tracer=self._tracer, meter=self._meter, event_logger=self._event_logger)
            if exporter_type_full
            else SpanMetricExporter(tracer=self._tracer, meter=self._meter)
        )

        self._llm_registry: dict[UUID, LLMInvocation] = {}
        self._tool_registry: dict[UUID, ToolInvocation] = {}
        self._lock = Lock()

    def start_llm(self, prompts: List[Message], tool_functions: List[ToolFunction], run_id: UUID, parent_run_id: Optional[UUID] = None, **attributes):
        invocation = LLMInvocation(messages=prompts , tool_functions=tool_functions, run_id=run_id, parent_run_id=parent_run_id, attributes=attributes)
        with self._lock:
            self._llm_registry[invocation.run_id] = invocation
        self._exporter.init_llm(invocation)

    def stop_llm(self, run_id: UUID, chat_generations: List[ChatGeneration], **attributes) -> LLMInvocation:
        with self._lock:
            invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.chat_generations = chat_generations
        invocation.attributes.update(attributes)
        self._exporter.export_llm(invocation)
        return invocation

    def fail_llm(self, run_id: UUID, error: Error, **attributes) -> LLMInvocation:
        with self._lock:
            invocation = self._llm_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.attributes.update(**attributes)
        self._exporter.error_llm(error, invocation)
        return invocation

    def start_tool(self, input_str: str, run_id: UUID, parent_run_id: Optional[UUID] = None, **attributes):
        invocation = ToolInvocation(input_str=input_str , run_id=run_id, parent_run_id=parent_run_id, attributes=attributes)
        with self._lock:
            self._tool_registry[invocation.run_id] = invocation
        self._exporter.init_tool(invocation)

    def stop_tool(self, run_id: UUID, output: ToolOutput, **attributes) -> ToolInvocation:
        with self._lock:
            invocation = self._tool_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.output = output
        self._exporter.export_tool(invocation)
        return invocation

    def fail_tool(self, run_id: UUID, error: Error, **attributes) -> ToolInvocation:
        with self._lock:
            invocation = self._tool_registry.pop(run_id)
        invocation.end_time = time.time()
        invocation.attributes.update(**attributes)
        self._exporter.error_tool(error, invocation)
        return invocation

# Singleton accessor
_default_client: TelemetryClient | None = None

def get_telemetry_client(exporter_type_full: bool = True, **kwargs) -> TelemetryClient:
    global _default_client
    if _default_client is None:
        _default_client = TelemetryClient(exporter_type_full=exporter_type_full, **kwargs)
    return _default_client

# Module‐level convenience functions
def llm_start(prompts: List[Message], run_id: UUID, parent_run_id: Optional[UUID] = None, **attributes):
    return get_telemetry_client().start_llm(prompts=prompts, run_id=run_id, parent_run_id=parent_run_id, **attributes)

def llm_stop(run_id: UUID, chat_generations: List[ChatGeneration], **attributes) -> LLMInvocation:
    return get_telemetry_client().stop_llm(run_id=run_id, chat_generations=chat_generations, **attributes)

def llm_fail(run_id: UUID, error: Error, **attributes) -> LLMInvocation:
    return get_telemetry_client().fail_llm(run_id=run_id, error=error, **attributes)
