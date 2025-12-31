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

"""Metrics instruments for Pinecone instrumentation."""

from opentelemetry.metrics import Meter

from opentelemetry.instrumentation.pinecone.semconv import Meters


def create_metrics(meter: Meter):
    """Create metrics instruments for Pinecone instrumentation.

    Args:
        meter: OpenTelemetry Meter instance

    Returns:
        Dictionary of metric instruments
    """
    return {
        "query_duration": meter.create_histogram(
            Meters.QUERY_DURATION,
            unit="s",
            description="Duration of query operations to Pinecone",
        ),
        "read_units": meter.create_counter(
            Meters.USAGE_READ_UNITS,
            unit="unit",
            description="Number of read units consumed in Pinecone calls",
        ),
        "write_units": meter.create_counter(
            Meters.USAGE_WRITE_UNITS,
            unit="unit",
            description="Number of write units consumed in Pinecone calls",
        ),
        "scores": meter.create_histogram(
            Meters.QUERY_SCORES,
            unit="score",
            description="Scores returned from Pinecone query calls",
        ),
    }
