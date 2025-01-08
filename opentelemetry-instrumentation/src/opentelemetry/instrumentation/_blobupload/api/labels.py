"""Provides utilities for providing basic identifying labels for blobs."""


def generate_labels_for_span(trace_id: str, span_id: str) -> dict:
    """Returns metadata for a span."""
    return {"otel_type": "span", "trace_id": trace_id, "span_id": span_id}


def generate_labels_for_event(
    trace_id: str, span_id: str, event_name: str
) -> dict:
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
) -> dict:
    """Returns metadata for a span event."""
    result = generate_labels_for_event(trace_id, span_id, event_name)
    result.update(
        {
            "otel_type": "span_event",
            "event_index": event_index,
        }
    )
    return result
