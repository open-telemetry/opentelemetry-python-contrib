import cohere

from opentelemetry import trace
from opentelemetry.instrumentation.cohere_v2 import CohereInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

CohereInstrumentor().instrument()

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(ConsoleSpanExporter())
)
tracer = trace.get_tracer(__name__)

co = cohere.ClientV2()

with tracer.start_as_current_span("foo"):
    response = co.chat(
        model="command-r-plus", 
        messages=[{"role": "user", "content": "Write a short poem on OpenTelemetry."}]
    )
