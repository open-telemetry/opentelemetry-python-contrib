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

"""OpenAI Agents instrumentation for OpenTelemetry."""

from __future__ import annotations

import os
from typing import Collection, Protocol

from agents import tracing
from agents.tracing.processor_interface import TracingProcessor

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .package import _instruments
from .span_processor import _OpenAIAgentsSpanProcessor
from .version import __version__  # noqa: F401


class _ProcessorHolder(Protocol):
    _processors: Collection[TracingProcessor]


class _TraceProviderLike(Protocol):
    _multi_processor: _ProcessorHolder


__all__ = ["OpenAIAgentsInstrumentor"]


def _resolve_system(_: str | None) -> str:
    # OpenAI spans must report provider name "openai" per semantic conventions.
    return GenAI.GenAiSystemValues.OPENAI.value


def _get_registered_processors(
    provider: _TraceProviderLike,
) -> list[TracingProcessor]:
    """Return tracing processors registered on the OpenAI Agents trace provider.

    The provider exposes a private `_multi_processor` attribute with a `_processors`
    collection that stores the currently registered processors in execution order.
    """
    multi = getattr(provider, "_multi_processor", None)
    processors = getattr(multi, "_processors", ())
    return list(processors)


class OpenAIAgentsInstrumentor(BaseInstrumentor):
    """Instrumentation that bridges OpenAI Agents tracing to OpenTelemetry spans."""

    def __init__(self) -> None:
        super().__init__()
        self._processor: _OpenAIAgentsSpanProcessor | None = None

    def _instrument(self, **kwargs) -> None:
        if self._processor is not None:
            return

        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        system = _resolve_system(kwargs.get("system"))
        agent_name_override = kwargs.get("agent_name") or os.getenv(
            "OTEL_GENAI_AGENT_NAME"
        )

        processor = _OpenAIAgentsSpanProcessor(
            tracer=tracer,
            system=system,
            agent_name_override=agent_name_override,
        )

        provider = tracing.get_trace_provider()
        existing = _get_registered_processors(provider)
        provider.set_processors([*existing, processor])
        self._processor = processor

    def _uninstrument(self, **kwargs) -> None:
        if self._processor is None:
            return

        provider = tracing.get_trace_provider()
        current = _get_registered_processors(provider)
        filtered = [proc for proc in current if proc is not self._processor]
        provider.set_processors(filtered)

        self._processor.shutdown()
        self._processor = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
