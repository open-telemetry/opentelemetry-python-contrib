# pylint: skip-file
import os

from openai import OpenAI

# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _events, _logs, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import (
    ExplicitBucketHistogramAggregation,
    View,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# configure metrics
reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(), export_interval_millis=1000
)

# Configure metric views that allow to customize the bucket boundaries for histogram metrics.
# This should not be necessary in the future - https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3235.
# The bucket boundaries ensure that the metrics are correctly aggregated and displayed in the backend.
#
# The bucket boundaries are defined as follows:
# For `gen_ai.client.token.usage`: [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]
# For `gen_ai.client.operation.duration`: [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]
#
# If your application benefits from different bucket boundaries, you can update them as needed.
views = [
    View(
        instrument_name="gen_ai.client.token.usage",
        aggregation=ExplicitBucketHistogramAggregation(
            [
                1,
                4,
                16,
                64,
                256,
                1024,
                4096,
                16384,
                65536,
                262144,
                1048576,
                4194304,
                16777216,
                67108864,
            ]
        ),
    ),
    View(
        instrument_name="gen_ai.client.operation.duration",
        aggregation=ExplicitBucketHistogramAggregation(
            [
                0.01,
                0.02,
                0.04,
                0.08,
                0.16,
                0.32,
                0.64,
                1.28,
                2.56,
                5.12,
                10.24,
                20.48,
                40.96,
                81.92,
            ]
        ),
    ),
]
set_meter_provider(MeterProvider(metric_readers=[reader], views=views))

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)
_events.set_event_logger_provider(EventLoggerProvider())

# instrument OpenAI
OpenAIInstrumentor().instrument()


def main():
    client = OpenAI()
    chat_completion = client.chat.completions.create(
        model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        messages=[
            {
                "role": "user",
                "content": "Write a short poem on OpenTelemetry.",
            },
        ],
    )
    print(chat_completion.choices[0].message.content)


if __name__ == "__main__":
    main()
