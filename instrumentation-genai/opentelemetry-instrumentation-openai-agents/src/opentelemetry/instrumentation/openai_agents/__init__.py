"""OpenAI Agents instrumentation.

Usage::

    from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor
    OpenAIAgentsInstrumentor().instrument()

This package integrates OpenAI agent framework spans with OpenTelemetry GenAI
semantic conventions as declared in `registry.yaml` and `spans.yaml`.
"""
from __future__ import annotations

import logging
from typing import Collection

from opentelemetry._events import get_event_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .genai_semantic_processor import GenAISemanticProcessor
from .package import _instruments

logger = logging.getLogger(__name__)


class OpenAIAgentsInstrumentor(BaseInstrumentor):
    _processor = None
    def instrumentation_dependencies(self) -> Collection[str]:  # noqa: D401
        return _instruments

    def _instrument(self, **kwargs):  # noqa: D401
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )
        event_logger_provider = kwargs.get("event_logger_provider")
        event_logger = get_event_logger(
            __name__,
            "",
            schema_url=Schemas.V1_28_0.value,
            event_logger_provider=event_logger_provider,
        )
        try:
            # Dynamically import agents tracing if available
            from agents.tracing import add_trace_processor  # type: ignore
        except Exception:  # pragma: no cover
            logger.warning(
                "agents.tracing not available - OpenAI Agents spans will not be created"
            )
            return

        if self._processor is None:
            self._processor = GenAISemanticProcessor(
                tracer=tracer, event_logger=event_logger
            )
            add_trace_processor(self._processor)
        else:
            logger.info("OpenAI Agents already instrumented; skipping duplicate registration")
        logger.info("OpenAI Agents instrumentation enabled")

    def _uninstrument(self, **kwargs):  # noqa: D401
        if self._processor is not None:
            try:
                self._processor.shutdown()
                logger.info("OpenAI Agents instrumentation deactivated (processor shutdown)")
            except Exception:  # pragma: no cover
                logger.debug("Failed to shutdown processor", exc_info=True)
        else:
            logger.info("OpenAI Agents instrumentation was not active")
