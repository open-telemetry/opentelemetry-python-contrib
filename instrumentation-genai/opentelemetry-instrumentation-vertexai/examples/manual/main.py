# pylint: skip-file
import vertexai
from vertexai.generative_models import GenerativeModel

# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _events, _logs, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)
_events.set_event_logger_provider(EventLoggerProvider())

# instrument VertexAI
VertexAIInstrumentor().instrument()


def main():
    vertexai.init()
    model = GenerativeModel("gemini-1.5-flash-002")
    chat_completion = model.generate_content(
        "Write a short poem on OpenTelemetry."
    )
    print(chat_completion.text)


if __name__ == "__main__":
    main()
