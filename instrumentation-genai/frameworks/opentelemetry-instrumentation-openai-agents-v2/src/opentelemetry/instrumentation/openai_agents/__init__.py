"""OpenAI Agents instrumentation for OpenTelemetry."""

# pylint: disable=too-many-locals

from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Collection

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .package import _instruments
from .span_processor import (
    ContentCaptureMode,
    GenAIEvaluationAttributes,
    GenAIOperationName,
    GenAIOutputType,
    GenAIProvider,
    GenAISemanticProcessor,
    GenAIToolType,
)

__all__ = [
    "OpenAIAgentsInstrumentor",
    "GenAIProvider",
    "GenAIOperationName",
    "GenAIToolType",
    "GenAIOutputType",
    "GenAIEvaluationAttributes",
]

logger = logging.getLogger(__name__)

_CONTENT_CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
_SYSTEM_OVERRIDE_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_SYSTEM"
_CAPTURE_CONTENT_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT"
_CAPTURE_METRICS_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS"


def _load_tracing_module():  # pragma: no cover - exercised via tests
    return importlib.import_module("agents.tracing")


def _get_registered_processors(provider) -> list:
    multi = getattr(provider, "_multi_processor", None)
    processors = getattr(multi, "_processors", ())
    return list(processors)


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


def _resolve_content_mode(value: Any) -> ContentCaptureMode:
    if isinstance(value, ContentCaptureMode):
        return value
    if isinstance(value, bool):
        return (
            ContentCaptureMode.SPAN_AND_EVENT
            if value
            else ContentCaptureMode.NO_CONTENT
        )

    if value is None:
        return ContentCaptureMode.SPAN_AND_EVENT

    text = str(value).strip().lower()
    if not text:
        return ContentCaptureMode.SPAN_AND_EVENT

    mapping = {
        "span_only": ContentCaptureMode.SPAN_ONLY,
        "span-only": ContentCaptureMode.SPAN_ONLY,
        "span": ContentCaptureMode.SPAN_ONLY,
        "event_only": ContentCaptureMode.EVENT_ONLY,
        "event-only": ContentCaptureMode.EVENT_ONLY,
        "event": ContentCaptureMode.EVENT_ONLY,
        "span_and_event": ContentCaptureMode.SPAN_AND_EVENT,
        "span-and-event": ContentCaptureMode.SPAN_AND_EVENT,
        "span_and_events": ContentCaptureMode.SPAN_AND_EVENT,
        "all": ContentCaptureMode.SPAN_AND_EVENT,
        "true": ContentCaptureMode.SPAN_AND_EVENT,
        "1": ContentCaptureMode.SPAN_AND_EVENT,
        "yes": ContentCaptureMode.SPAN_AND_EVENT,
        "no_content": ContentCaptureMode.NO_CONTENT,
        "false": ContentCaptureMode.NO_CONTENT,
        "0": ContentCaptureMode.NO_CONTENT,
        "no": ContentCaptureMode.NO_CONTENT,
        "none": ContentCaptureMode.NO_CONTENT,
    }

    return mapping.get(text, ContentCaptureMode.SPAN_AND_EVENT)


def _resolve_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


class OpenAIAgentsInstrumentor(BaseInstrumentor):
    """Instrumentation that bridges OpenAI Agents tracing to OpenTelemetry."""

    def __init__(self) -> None:
        super().__init__()
        self._processor: GenAISemanticProcessor | None = None

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
            _SYSTEM_OVERRIDE_ENV
        )
        system = _resolve_system(system_override)

        content_override = kwargs.get("capture_message_content")
        if content_override is None:
            content_override = os.getenv(_CONTENT_CAPTURE_ENV) or os.getenv(
                _CAPTURE_CONTENT_ENV
            )
        content_mode = _resolve_content_mode(content_override)

        metrics_override = kwargs.get("capture_metrics")
        if metrics_override is None:
            metrics_override = os.getenv(_CAPTURE_METRICS_ENV)
        metrics_enabled = _resolve_bool(metrics_override, default=True)

        agent_name = kwargs.get("agent_name")
        agent_id = kwargs.get("agent_id")
        agent_description = kwargs.get("agent_description")
        base_url = kwargs.get("base_url")
        server_address = kwargs.get("server_address")
        server_port = kwargs.get("server_port")

        processor = GenAISemanticProcessor(
            tracer=tracer,
            system_name=system,
            include_sensitive_data=content_mode
            != ContentCaptureMode.NO_CONTENT,
            content_mode=content_mode,
            metrics_enabled=metrics_enabled,
            agent_name=agent_name,
            agent_id=agent_id,
            agent_description=agent_description,
            base_url=base_url,
            server_address=server_address,
            server_port=server_port,
            agent_name_default="OpenAI Agent",
            agent_id_default="agent",
            agent_description_default="OpenAI Agents instrumentation",
            base_url_default="https://api.openai.com",
            server_address_default="api.openai.com",
            server_port_default=443,
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

        try:
            self._processor.shutdown()
        finally:
            self._processor = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
