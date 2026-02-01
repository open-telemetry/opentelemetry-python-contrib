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

"""Processors for OTLP Collector."""

from opentelemetry.exporter.clickhouse_genai.processors.batch_processor import (
    BatchProcessor,
)
from opentelemetry.exporter.clickhouse_genai.processors.transform import (
    otlp_logs_to_rows,
    otlp_metrics_to_rows,
    otlp_spans_to_rows,
)

__all__ = [
    "BatchProcessor",
    "otlp_spans_to_rows",
    "otlp_logs_to_rows",
    "otlp_metrics_to_rows",
]
