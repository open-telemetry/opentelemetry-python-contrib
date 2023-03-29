from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
import urllib3

URLLib3Instrumentor().instrument(
    excluded_urls="https://www.example.com",
)

http = urllib3.PoolManager()

provider = TracerProvider()
processor = BatchSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("Request parent span") as span:
    response = http.request("GET", "https://www.example.com/")
    response2 = http.request("GET", "https://www.example.org/")

input()