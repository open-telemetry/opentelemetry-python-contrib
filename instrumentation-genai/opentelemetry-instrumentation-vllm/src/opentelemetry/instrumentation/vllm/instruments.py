# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

# Bucket boundaries for server-side latency metrics (seconds)
_GEN_AI_SERVER_LATENCY_BUCKETS = [
    0.001,
    0.005,
    0.01,
    0.02,
    0.04,
    0.06,
    0.08,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
]

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


class Instruments:
    def __init__(self, meter: Meter):
        self.server_ttft_histogram: Histogram = meter.create_histogram(
            name=gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN,
            description="Time to generate first token on the server",
            unit="s",
            explicit_bucket_boundaries_advisory=_GEN_AI_SERVER_LATENCY_BUCKETS,
        )
        self.server_tpot_histogram: Histogram = meter.create_histogram(
            name=gen_ai_metrics.GEN_AI_SERVER_TIME_PER_OUTPUT_TOKEN,
            description="Time per output token on the server",
            unit="s",
            explicit_bucket_boundaries_advisory=_GEN_AI_SERVER_LATENCY_BUCKETS,
        )
        self.client_operation_duration_histogram: Histogram = (
            meter.create_histogram(
                name=gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION,
                description="GenAI operation duration",
                unit="s",
                explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS,
            )
        )
        self.client_token_usage_histogram: Histogram = meter.create_histogram(
            name=gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE,
            description="Measures number of input and output tokens used",
            unit="{token}",
            explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS,
        )
