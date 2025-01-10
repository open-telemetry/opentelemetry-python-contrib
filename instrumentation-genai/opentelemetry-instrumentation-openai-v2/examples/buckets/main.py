import os

from openai import OpenAI

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk.metrics import Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import (
    ExplicitBucketHistogramAggregation,
    View,
)

# configure metrics
metric_exporter = OTLPMetricExporter()
metric_reader = PeriodicExportingMetricReader(metric_exporter)

TokenUsageHistogramView = View(
    instrument_type=Histogram,
    instrument_name="gen_ai.client.token.usage",
    aggregation=ExplicitBucketHistogramAggregation(
        boundaries=[
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
)

DurationHistogramView = View(
    instrument_type=Histogram,
    instrument_name="gen_ai.client.operation.duration",
    aggregation=ExplicitBucketHistogramAggregation(
        boundaries=[
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
)

meter_provider = MeterProvider(
    metric_readers=[metric_reader],
    views=[TokenUsageHistogramView, DurationHistogramView],
)
metrics.set_meter_provider(meter_provider)

# instrument OpenAI
OpenAIInstrumentor().instrument(meter_provider=meter_provider)


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
