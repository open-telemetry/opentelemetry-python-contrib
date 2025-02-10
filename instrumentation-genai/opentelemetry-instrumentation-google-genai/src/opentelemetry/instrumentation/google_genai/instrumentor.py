from typing import Any, Collection

from opentelemetry.trace import get_tracer_provider
from opentelemetry.metrics import get_meter_provider
from opentelemetry._events import get_event_logger_provider 
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

from .generate_content import instrument_generate_content, uninstrument_generate_content
from .otel_wrapper import OTelWrapper


class GoogleGenAiSdkInstrumentor(BaseInstrumentor):

    def __init__(self):
        self._generate_content_snapshot = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return ['google-genai>=1.0.0,<2']

    def _instrument(self, **kwargs: Any):
        tracer_provider = kwargs.get('tracer_provider') or get_tracer_provider()
        event_logger_provider = kwargs.get('event_logger_provider') or get_event_logger_provider()
        meter_provider = kwargs.get('meter_provider') or get_meter_provider()
        otel_wrapper = OTelWrapper.from_providers(
            tracer_provider=tracer_provider,
            event_logger_provider=event_logger_provider,
            meter_provider=meter_provider,
        )
        self._generate_content_snapshot = instrument_generate_content(otel_wrapper)

    def _uninstrument(self, **kwargs: Any):
        uninstrument_generate_content(self._generate_content_snapshot)

