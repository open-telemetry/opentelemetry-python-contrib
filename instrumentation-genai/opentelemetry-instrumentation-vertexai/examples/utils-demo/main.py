# pylint: skip-file
"""
invoke_agent instrumentation demo.

Combines automatic instrumentation (``VertexAIInstrumentor``) with
manual ``TelemetryHandler.agent()`` spans from ``opentelemetry-util-genai``
to show how genai-utils extends the existing Vertex AI instrumentation
with agent invocation lifecycle spans.

The ``generate_content`` call is made inside the ``invoke_agent`` context,
so the auto-instrumented LLM span appears as a child of the ``invoke_agent``
parent span.

Set environment variables before running:

    export GCP_PROJECT="your-project-id"
    python main.py
"""

import os

import vertexai
from vertexai.generative_models import GenerativeModel

# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import AgentInvocation

OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "gcp-o11yinframon-nprd-81065")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MODEL = "gemini-2.5-flash"
AGENT_NAME = "Currency Exchange Agent"

resource = Resource.create({"service.name": "invoke-agent-demo"})

# configure tracing
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
trace.set_tracer_provider(tracer_provider)

# configure metrics
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True)
)
meter_provider = MeterProvider(
    resource=resource, metric_readers=[metric_reader]
)
metrics.set_meter_provider(meter_provider)

# configure logging and events
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    )
)
_logs.set_logger_provider(logger_provider)

# Auto-instrument Vertex AI SDK calls (generate_content, etc.)
VertexAIInstrumentor().instrument()


def main():
    vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION)
    model = GenerativeModel(MODEL)
    handler = TelemetryHandler()

    # ----- invoke_agent span wrapping an LLM call -----
    # The generate_content call is auto-instrumented by VertexAIInstrumentor
    # and appears as a child span under the invoke_agent parent span.
    print("[invoke_agent] Starting agent invocation...")
    with handler.agent(
        AgentInvocation(
            agent_name=AGENT_NAME,
            provider="gcp_vertex_ai",
            request_model=MODEL,
            agent_description="Currency exchange agent demo",
            server_address=f"{GCP_LOCATION}-aiplatform.googleapis.com",
        )
    ) as invocation:
        response = model.generate_content(
            "What is the exchange rate from US dollars to SEK today?"
        )
        # Populate response attributes on the invocation
        usage = response.usage_metadata
        invocation.input_tokens = usage.prompt_token_count
        invocation.output_tokens = usage.candidates_token_count
        invocation.finish_reasons = ["stop"]

    print(f"[invoke_agent] Response:\n{response.text}\n")


if __name__ == "__main__":
    main()
