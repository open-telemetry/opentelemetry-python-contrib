import sys
sys.path.append('../../src')

from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

class InstrumentationContext:

    def __init__(self):
        self._instrumentor = GoogleGenAiSdkInstrumentor()

    def install(self):
        self._instrumentor.instrument()

    def uninstall(self):
        self._instrumentor.uninstrument()
