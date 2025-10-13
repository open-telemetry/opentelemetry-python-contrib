"""OpenAI Agents instrumentation for OpenTelemetry."""

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

from .constants import (
    GenAIEvaluationAttributes,
    GenAIOperationName,
    GenAIOutputType,
    GenAIProvider,
    GenAIToolType,
)
from .genai_semantic_processor import (
    ContentCaptureMode,
    GenAISemanticProcessor,
)
from .package import _instruments

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


_AGENT_NAME_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_AGENT_NAME"
_AGENT_ID_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_AGENT_ID"
_AGENT_DESCRIPTION_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_AGENT_DESCRIPTION"
_BASE_URL_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_BASE_URL"
_SERVER_ADDRESS_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_SERVER_ADDRESS"
_SERVER_PORT_ENV = "OTEL_INSTRUMENTATION_OPENAI_AGENTS_SERVER_PORT"


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


def _resolve_optional_str(value: Any, env_name: str) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            return candidate
    elif value is not None:
        candidate = str(value).strip()
        if candidate:
            return candidate
    env_val = os.getenv(env_name)
    if env_val and env_val.strip():
        return env_val.strip()
    return None


def _resolve_optional_int(value: Any, env_name: str) -> int | None:
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.debug(
                "Invalid integer override for %s: %r", env_name, value
            )
            return None
    env_val = os.getenv(env_name)
    if env_val and env_val.strip():
        try:
            return int(env_val)
        except ValueError:
            logger.debug("Invalid integer from env %s: %r", env_name, env_val)
    return None


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

        agent_name = _resolve_optional_str(
            kwargs.get("agent_name"), _AGENT_NAME_ENV
        )
        agent_id = _resolve_optional_str(kwargs.get("agent_id"), _AGENT_ID_ENV)
        agent_description = _resolve_optional_str(
            kwargs.get("agent_description"), _AGENT_DESCRIPTION_ENV
        )
        base_url = _resolve_optional_str(kwargs.get("base_url"), _BASE_URL_ENV)
        server_address = _resolve_optional_str(
            kwargs.get("server_address"), _SERVER_ADDRESS_ENV
        )
        server_port = _resolve_optional_int(
            kwargs.get("server_port"), _SERVER_PORT_ENV
        )

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
