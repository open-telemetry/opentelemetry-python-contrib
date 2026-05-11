# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase

import wrapt
from aio_pika import Exchange, Queue

from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor


class TestPika(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = AioPikaInstrumentor()
        instrumentation.instrument()
        self.assertTrue(isinstance(Queue.consume, wrapt.BoundFunctionWrapper))
        self.assertTrue(
            isinstance(Exchange.publish, wrapt.BoundFunctionWrapper)
        )
        instrumentation.uninstrument()
        self.assertFalse(isinstance(Queue.consume, wrapt.BoundFunctionWrapper))
        self.assertFalse(
            isinstance(Exchange.publish, wrapt.BoundFunctionWrapper)
        )
