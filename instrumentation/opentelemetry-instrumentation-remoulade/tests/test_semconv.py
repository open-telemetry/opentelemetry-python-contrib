# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
from unittest import mock

import remoulade
from remoulade.brokers.local import LocalBroker

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.remoulade import RemouladeInstrumentor
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


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


@remoulade.actor
def actor_multiply(x, y):
    return x * y


class TestRemouladeSemConv(TestBase):
    def setUp(self):
        super().setUp()
        self._broker = LocalBroker()
        remoulade.set_broker(self._broker)
        self._broker.declare_actor(actor_multiply)

    def tearDown(self):
        RemouladeInstrumentor().uninstrument()
        super().tearDown()

    def _run_actor_and_get_spans(self):
        RemouladeInstrumentor().instrument()
        actor_multiply.send(6, 7)
        return self.sorted_spans(self.memory_exporter.get_finished_spans())

    def _assert_common_attributes(self, spans):
        consumer, producer = spans
        self.assertEqual(consumer.name, "remoulade/process")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertEqual(producer.name, "remoulade/send")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        # messaging.message.id is identical in old and new conventions.
        self.assertEqual(
            consumer.attributes.get(MESSAGING_MESSAGE_ID),
            producer.attributes.get(MESSAGING_MESSAGE_ID),
        )
        self.assertIsNotNone(consumer.attributes.get(MESSAGING_MESSAGE_ID))
        # Remoulade-specific attributes are unaffected by the opt-in.
        for span, action in ((consumer, "run"), (producer, "send")):
            self.assertEqual(span.attributes.get("remoulade.action"), action)
            self.assertEqual(span.attributes.get("remoulade.actor_name"), "actor_multiply")

    @stability_mode("")
    def test_default_mode_schema_url(self):
        spans = self._run_actor_and_get_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(
                span.instrumentation_scope.schema_url,
                "https://opentelemetry.io/schemas/1.11.0",
            )
        self._assert_common_attributes(spans)

    @stability_mode("messaging")
    def test_new_mode_schema_url(self):
        spans = self._run_actor_and_get_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(
                span.instrumentation_scope.schema_url,
                "https://opentelemetry.io/schemas/1.44.0",
            )
        self._assert_common_attributes(spans)

    @stability_mode("messaging/dup")
    def test_dup_mode_schema_url(self):
        spans = self._run_actor_and_get_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(
                span.instrumentation_scope.schema_url,
                "https://opentelemetry.io/schemas/1.44.0",
            )
        self._assert_common_attributes(spans)


if __name__ == "__main__":
    import unittest

    unittest.main()
