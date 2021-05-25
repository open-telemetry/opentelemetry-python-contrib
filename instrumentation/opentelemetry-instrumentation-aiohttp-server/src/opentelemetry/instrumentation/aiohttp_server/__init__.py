from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


class AioHttpServerInstrumentor(BaseInstrumentor):
    def _uninstrument(self, **kwargs):
        pass

    def _instrument(self, **kwargs):
        pass
