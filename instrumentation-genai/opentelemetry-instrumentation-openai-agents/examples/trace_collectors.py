"""Trace collectors showcase: Console, OTLP gRPC/HTTP, Azure Monitor.

Run with appropriate env vars:
- OTLP_GRPC_ENDPOINT (e.g., http://localhost:4317)
- OTLP_HTTP_ENDPOINT (e.g., http://localhost:4318/v1/traces)
- APPLICATION_INSIGHTS_CONNECTION_STRING
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as OTLPGrpcSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as OTLPHttpSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)


def configure_trace_collectors() -> None:
    resource = Resource.create(
        {
            "service.name": "openai-agents-trace-collectors",
            "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        }
    )
    tp = TracerProvider(resource=resource)

    # Console
    tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # OTLP gRPC
    otlp_grpc_endpoint = os.getenv("OTLP_GRPC_ENDPOINT")
    if otlp_grpc_endpoint:
        tp.add_span_processor(
            BatchSpanProcessor(
                OTLPGrpcSpanExporter(endpoint=otlp_grpc_endpoint)
            )
        )

    # OTLP HTTP
    otlp_http_endpoint = os.getenv("OTLP_HTTP_ENDPOINT")
    if otlp_http_endpoint:
        tp.add_span_processor(
            BatchSpanProcessor(
                OTLPHttpSpanExporter(endpoint=otlp_http_endpoint)
            )
        )

    # Azure Monitor
    conn = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
    if conn:
        try:
            from azure.monitor.opentelemetry.exporter import (
                AzureMonitorTraceExporter,
            )
        except ImportError:
            print(
                "Azure Monitor exporter not installed. "
                "Install: pip install azure-monitor-opentelemetry-exporter",
            )
        else:
            tp.add_span_processor(
                BatchSpanProcessor(
                    AzureMonitorTraceExporter.from_connection_string(conn)
                )
            )

    trace.set_tracer_provider(tp)


def main():
    configure_trace_collectors()
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("trace-collectors-demo"):
        print("Trace collectors configured and demo span emitted.")


if __name__ == "__main__":
    main()
