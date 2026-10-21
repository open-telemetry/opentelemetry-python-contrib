# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
import threading
import time
from unittest import mock

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.celery import CeleryInstrumentor, utils
from opentelemetry.sdk import trace
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_DESTINATION_NAME,
    MESSAGING_MESSAGE_CONVERSATION_ID,
    MESSAGING_MESSAGE_ID,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase

from .celery_test_tasks import app, task_add


def stability_mode(mode):
    def decorator(test_case):
        @mock.patch.dict(os.environ, {OTEL_SEMCONV_STABILITY_OPT_IN: mode})
        def wrapper(*args, **kwargs):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            try:
                return test_case(*args, **kwargs)
            finally:
                # Restore the default (old conventions) state so other
                # tests in the same process are not affected.
                _OpenTelemetrySemanticConventionStability._initialized = False
                os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
                _OpenTelemetrySemanticConventionStability._initialize()

        return wrapper

    return decorator


def _make_span():
    return trace._Span("name", mock.Mock(spec=trace_api.SpanContext))


def _declare(exchange_type):
    declare = mock.Mock()
    declare.exchange.type = exchange_type
    return declare


def _context():
    return {
        "correlation_id": "44b7f305",
        "delivery_info": {"routing_key": "celery"},
        "eta": "soon",
        "hostname": "localhost",
        "id": "44b7f305",
        "routing_key": "celery",
        "declare": [_declare("direct"), _declare("topic")],
    }


class TestCelerySemConvAttributes(TestBase):
    @stability_mode("")
    def test_default_mode_reports_old_attributes(self):
        span = _make_span()
        utils.set_attributes_from_context(span, _context())

        self.assertEqual(span.attributes.get(SpanAttributes.MESSAGING_DESTINATION), "celery")
        self.assertIsInstance(span.attributes.get(SpanAttributes.MESSAGING_DESTINATION), str)
        self.assertEqual(
            span.attributes.get(SpanAttributes.MESSAGING_CONVERSATION_ID),
            "44b7f305",
        )
        self.assertEqual(span.attributes.get(SpanAttributes.MESSAGING_DESTINATION_KIND), "queue")
        self.assertEqual(span.attributes.get(MESSAGING_MESSAGE_ID), "44b7f305")
        # New attributes must not be reported in default mode.
        self.assertNotIn(MESSAGING_DESTINATION_NAME, span.attributes)
        self.assertNotIn(MESSAGING_MESSAGE_CONVERSATION_ID, span.attributes)
        # Unrelated celery attributes are unaffected.
        self.assertEqual(span.attributes.get("celery.eta"), "soon")
        self.assertEqual(span.attributes.get("celery.hostname"), "localhost")

    @stability_mode("messaging")
    def test_new_mode_reports_new_attributes_only(self):
        span = _make_span()
        utils.set_attributes_from_context(span, _context())

        self.assertEqual(span.attributes.get(MESSAGING_DESTINATION_NAME), "celery")
        self.assertIsInstance(span.attributes.get(MESSAGING_DESTINATION_NAME), str)
        self.assertEqual(span.attributes.get(MESSAGING_MESSAGE_CONVERSATION_ID), "44b7f305")
        # messaging.message.id is unchanged across conventions.
        self.assertEqual(span.attributes.get(MESSAGING_MESSAGE_ID), "44b7f305")
        # Old attributes must not be reported in new-only mode, and
        # messaging.destination.kind has no replacement in the new conventions.
        self.assertNotIn(SpanAttributes.MESSAGING_DESTINATION, span.attributes)
        self.assertNotIn(SpanAttributes.MESSAGING_CONVERSATION_ID, span.attributes)
        self.assertNotIn(SpanAttributes.MESSAGING_DESTINATION_KIND, span.attributes)

    @stability_mode("messaging/dup")
    def test_dup_mode_reports_both_attributes(self):
        span = _make_span()
        utils.set_attributes_from_context(span, _context())

        self.assertEqual(span.attributes.get(SpanAttributes.MESSAGING_DESTINATION), "celery")
        self.assertEqual(span.attributes.get(MESSAGING_DESTINATION_NAME), "celery")
        self.assertEqual(
            span.attributes.get(SpanAttributes.MESSAGING_CONVERSATION_ID),
            "44b7f305",
        )
        self.assertEqual(span.attributes.get(MESSAGING_MESSAGE_CONVERSATION_ID), "44b7f305")
        self.assertEqual(span.attributes.get(SpanAttributes.MESSAGING_DESTINATION_KIND), "queue")
        self.assertEqual(span.attributes.get(MESSAGING_MESSAGE_ID), "44b7f305")


class TestCelerySemConvSchemaUrl(TestBase):
    def setUp(self):
        super().setUp()
        self._worker = app.Worker(app=app, pool="solo", concurrency=1)
        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        super().tearDown()
        CeleryInstrumentor().uninstrument()
        self._worker.stop()
        self._thread.join()
        CeleryInstrumentor().uninstrument()

    def _run_task_and_get_spans(self):
        CeleryInstrumentor().instrument()
        result = task_add.delay(1, 2)
        timeout = time.time() + 60
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)
        return self.sorted_spans(self.memory_exporter.get_finished_spans())

    @stability_mode("")
    def test_default_mode_schema_url(self):
        spans = self._run_task_and_get_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(
                span.instrumentation_scope.schema_url,
                "https://opentelemetry.io/schemas/1.11.0",
            )

    @stability_mode("messaging")
    def test_new_mode_schema_url(self):
        spans = self._run_task_and_get_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(
                span.instrumentation_scope.schema_url,
                "https://opentelemetry.io/schemas/1.44.0",
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
