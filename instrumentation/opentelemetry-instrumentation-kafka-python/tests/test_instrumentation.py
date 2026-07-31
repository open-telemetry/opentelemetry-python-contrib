# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase

from kafka import KafkaConsumer, KafkaProducer
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.kafka import KafkaInstrumentor
from opentelemetry.instrumentation.kafka.package import _instruments


class TestKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = KafkaInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(KafkaProducer.send, BoundFunctionWrapper))
        self.assertTrue(
            isinstance(KafkaConsumer.__next__, BoundFunctionWrapper)
        )

        instrumentation.uninstrument()
        self.assertFalse(isinstance(KafkaProducer.send, BoundFunctionWrapper))
        self.assertFalse(
            isinstance(KafkaConsumer.__next__, BoundFunctionWrapper)
        )

    def test_instrumentation_dependencies(self) -> None:
        instrumentation = KafkaInstrumentor()

        self.assertEqual(
            instrumentation.instrumentation_dependencies(), _instruments
        )
