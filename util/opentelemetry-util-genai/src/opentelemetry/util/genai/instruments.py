from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS = [
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

_GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS = [
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

GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK = (
    "gen_ai.client.operation.time_to_first_chunk"
)

_GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK_BUCKETS = [
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


def create_duration_histogram(meter: Meter) -> Histogram:
    return meter.create_histogram(
        name=gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION,
        description="Duration of GenAI client operation",
        unit="s",
        explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS,
    )


def create_token_histogram(meter: Meter) -> Histogram:
    return meter.create_histogram(
        name=gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE,
        description="Number of input and output tokens used by GenAI clients",
        unit="{token}",
        explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS,
    )


def create_ttfc_histogram(meter: Meter) -> Histogram:
    return meter.create_histogram(
        name=GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK,
        description="Time to receive the first chunk in a streaming response",
        unit="s",
        explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK_BUCKETS,
    )


def get_metric_data_points(metric_reader, metric_name):
    """Extract all data points for a given metric name from a metric reader."""
    results = []
    metrics = metric_reader.get_metrics_data().resource_metrics
    if not metrics:
        return results
    for scope_metrics in metrics[0].scope_metrics:
        for m in scope_metrics.metrics:
            if m.name == metric_name:
                results.extend(m.data.data_points)
    return results
