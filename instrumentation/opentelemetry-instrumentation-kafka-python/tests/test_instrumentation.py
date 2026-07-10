# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase

from kafka import KafkaConsumer, KafkaProducer
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.kafka import KafkaInstrumentor


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
