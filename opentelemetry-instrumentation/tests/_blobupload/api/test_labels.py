#! /usr/bin/env python3

if __name__ == "__main__":
    import sys
    sys.path.append("../../../src")

import logging
import unittest

from opentelemetry.instrumentation._blobupload.api import (
    generate_labels_for_event,
    generate_labels_for_span,
    generate_labels_for_span_event,
)


class TestLabels(unittest.TestCase):
    def test_generate_labels_for_span(self):
        trace_id = "test-trace-id"
        span_id = "test-span-id"
        labels = generate_labels_for_span(trace_id=trace_id, span_id=span_id)
        self.assertEqual(
            labels,
            {
                "otel_type": "span",
                "trace_id": "test-trace-id",
                "span_id": "test-span-id",
            },
        )

    def test_generate_labels_for_event(self):
        trace_id = "test-trace-id"
        span_id = "test-span-id"
        event_name = "some-event"
        labels = generate_labels_for_event(
            trace_id=trace_id, span_id=span_id, event_name=event_name
        )
        self.assertEqual(
            labels,
            {
                "otel_type": "event",
                "trace_id": "test-trace-id",
                "span_id": "test-span-id",
                "event_name": "some-event",
            },
        )

    def test_generate_labels_for_span_event(self):
        trace_id = "test-trace-id"
        span_id = "test-span-id"
        event_name = "some-event"
        event_index = 2
        labels = generate_labels_for_span_event(
            trace_id=trace_id,
            span_id=span_id,
            event_name=event_name,
            event_index=event_index,
        )
        self.assertEqual(
            labels,
            {
                "otel_type": "span_event",
                "trace_id": "test-trace-id",
                "span_id": "test-span-id",
                "event_name": "some-event",
                "event_index": 2,
            },
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
