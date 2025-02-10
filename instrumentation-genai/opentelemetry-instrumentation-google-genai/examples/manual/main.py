import google.genai

# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _events as otel_events
from opentelemetry import _logs as otel_logs
from opentelemetry import trace as otel_trace
from opentelemetry import metrics as otel_metrics
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
)

def setup_otel_tracing():
    otel_trace.set_tracer_provider(TracerProvider())
    otel_trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )


def setup_otel_logs_and_events():
    otel_logs.set_logger_provider(LoggerProvider())
    otel_logs.get_logger_provider().add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter())
    )
    otel_events.set_event_logger_provider(EventLoggerProvider())


def setup_otel_metrics():
    meter_provider = MeterProvider(
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
            ),
        ]
    )
    otel_metrics.set_meter_provider(meter_provider)


def setup_opentelemetry():
    setup_otel_tracing()
    setup_otel_logs_and_events()
    setup_otel_metrics()


def instrument_google_genai():
    GoogleGenAiSdkInstrumentor().instrument()
    RequestsInstrumentor().instrument()


def main():
    setup_opentelemetry()
    instrument_google_genai()
    client = google.genai.Client()
    response = client.models.generate_content(
        model = os.getenv('MODEL', 'gemini-2.0-flash-001'),
        contents = os.getenv('PROMPT', 'Why is the sky blue?'),
    )
    print(response.text)


if __name__ == "__main__":
    main()
