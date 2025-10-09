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

import importlib
import os
from typing import Any, Collection

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .package import _instruments
from .span_processor import _ContentCaptureMode, _OpenAIAgentsSpanProcessor
from .version import __version__  # noqa: F401

__all__ = ["OpenAIAgentsInstrumentor"]

_CONTENT_CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"


def _load_tracing_module():
    return importlib.import_module("agents.tracing")


def _resolve_system(value: str | None) -> str:
    if not value:
        return GenAI.GenAiSystemValues.OPENAI.value

    normalized = value.strip().lower()
    for member in GenAI.GenAiSystemValues:
        if normalized == member.value:
            return member.value
        if normalized == member.name.lower():
            return member.value
    return value


def _get_registered_processors(provider) -> list:
    multi = getattr(provider, "_multi_processor", None)
    processors = getattr(multi, "_processors", ())
    return list(processors)


def _resolve_content_mode(value: Any) -> _ContentCaptureMode:
    if isinstance(value, _ContentCaptureMode):
        return value
    if isinstance(value, bool):
        return (
            _ContentCaptureMode.SPAN_AND_EVENT
            if value
            else _ContentCaptureMode.NO_CONTENT
        )

    if value is None:
        return _ContentCaptureMode.SPAN_AND_EVENT

    text = str(value).strip().lower()
    if not text:
        return _ContentCaptureMode.SPAN_AND_EVENT

    mapping = {
        "span_only": _ContentCaptureMode.SPAN_ONLY,
        "span-only": _ContentCaptureMode.SPAN_ONLY,
        "span": _ContentCaptureMode.SPAN_ONLY,
        "event_only": _ContentCaptureMode.EVENT_ONLY,
        "event-only": _ContentCaptureMode.EVENT_ONLY,
        "event": _ContentCaptureMode.EVENT_ONLY,
        "span_and_event": _ContentCaptureMode.SPAN_AND_EVENT,
        "span-and-event": _ContentCaptureMode.SPAN_AND_EVENT,
        "span_and_events": _ContentCaptureMode.SPAN_AND_EVENT,
        "all": _ContentCaptureMode.SPAN_AND_EVENT,
        "true": _ContentCaptureMode.SPAN_AND_EVENT,
        "1": _ContentCaptureMode.SPAN_AND_EVENT,
        "yes": _ContentCaptureMode.SPAN_AND_EVENT,
        "no_content": _ContentCaptureMode.NO_CONTENT,
        "false": _ContentCaptureMode.NO_CONTENT,
        "0": _ContentCaptureMode.NO_CONTENT,
        "no": _ContentCaptureMode.NO_CONTENT,
        "none": _ContentCaptureMode.NO_CONTENT,
    }

    return mapping.get(text, _ContentCaptureMode.SPAN_AND_EVENT)


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

        system_override = kwargs.get("system") or os.getenv(
            "OTEL_INSTRUMENTATION_OPENAI_AGENTS_SYSTEM"
        )
        system = _resolve_system(system_override)

        content_override = kwargs.get("capture_message_content")
        if content_override is None:
            content_override = os.getenv(_CONTENT_CAPTURE_ENV)

        content_mode = _resolve_content_mode(content_override)

        processor = _OpenAIAgentsSpanProcessor(
            tracer=tracer,
            system=system,
            content_mode=content_mode,
        )

        tracing = _load_tracing_module()
        provider = tracing.get_trace_provider()
        existing = _get_registered_processors(provider)
        provider.set_processors([*existing, processor])
        self._processor = processor

    def _uninstrument(self, **kwargs) -> None:
        if self._processor is None:
            return

        tracing = _load_tracing_module()
        provider = tracing.get_trace_provider()
        current = _get_registered_processors(provider)
        filtered = [proc for proc in current if proc is not self._processor]
        provider.set_processors(filtered)

        self._processor.shutdown()
        self._processor = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
