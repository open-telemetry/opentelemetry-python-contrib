from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

class CherryPyInstrumentor(BaseInstrumentor):
    """An instrumentor for FastAPI

    See `BaseInstrumentor`
    """

    def _instrument(self, **kwargs):
        pass

    def _uninstrument(self, **kwargs):
        pass
