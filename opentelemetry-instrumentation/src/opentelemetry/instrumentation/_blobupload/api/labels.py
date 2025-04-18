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

"""Provides utilities for providing basic identifying labels for blobs."""


def generate_labels_for_span(trace_id: str, span_id: str) -> dict[str, str]:
    """Returns metadata for a span."""
    return {"otel_type": "span", "trace_id": trace_id, "span_id": span_id}


def generate_labels_for_event(
    trace_id: str, span_id: str, event_name: str
) -> dict[str, str]:
    """Returns metadata for an event."""
    result = generate_labels_for_span(trace_id, span_id)
    result.update(
        {
            "otel_type": "event",
            "event_name": event_name,
        }
    )
    return result


def generate_labels_for_span_event(
    trace_id: str, span_id: str, event_name: str, event_index: int
) -> dict[str, str]:
    """Returns metadata for a span event."""
    result = generate_labels_for_event(trace_id, span_id, event_name)
    result.update(
        {
            "otel_type": "span_event",
            "event_index": event_index,
        }
    )
    return result
