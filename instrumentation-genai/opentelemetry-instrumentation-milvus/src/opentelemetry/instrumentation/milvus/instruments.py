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

"""Metrics instruments for Milvus instrumentation."""

from opentelemetry.metrics import Meter

from opentelemetry.instrumentation.milvus.semconv import Meters


def create_metrics(meter: Meter):
    """Create metrics instruments for Milvus instrumentation.

    Args:
        meter: OpenTelemetry Meter instance

    Returns:
        Dictionary of metric instruments
    """
    return {
        "query_duration": meter.create_histogram(
            Meters.QUERY_DURATION,
            unit="s",
            description="Duration of query operations to Milvus",
        ),
        "distance": meter.create_histogram(
            Meters.SEARCH_DISTANCE,
            unit="",
            description="Distance between search query vector and matched vectors",
        ),
        "insert_units": meter.create_counter(
            Meters.USAGE_INSERT_UNITS,
            unit="",
            description="Number of insert units consumed in Milvus calls",
        ),
        "upsert_units": meter.create_counter(
            Meters.USAGE_UPSERT_UNITS,
            unit="",
            description="Number of upsert units consumed in Milvus calls",
        ),
        "delete_units": meter.create_counter(
            Meters.USAGE_DELETE_UNITS,
            unit="",
            description="Number of delete units consumed in Milvus calls",
        ),
    }
