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
from unittest import TestCase

import aio_pika

from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor
from opentelemetry.instrumentation.aio_pika.instrumented_exchange import (
    InstrumentedExchange,
    RobustInstrumentedExchange,
)
from opentelemetry.instrumentation.aio_pika.instrumented_queue import (
    InstrumentedQueue,
    RobustInstrumentedQueue,
)


class TestPika(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = AioPikaInstrumentor()
        instrumentation.instrument()
        self.assertTrue(
            aio_pika.Channel.EXCHANGE_CLASS == InstrumentedExchange
        )
        self.assertTrue(aio_pika.Channel.QUEUE_CLASS == InstrumentedQueue)
        self.assertTrue(
            aio_pika.RobustChannel.EXCHANGE_CLASS == RobustInstrumentedExchange
        )
        self.assertTrue(
            aio_pika.RobustChannel.QUEUE_CLASS == RobustInstrumentedQueue
        )

        instrumentation.uninstrument()
        self.assertFalse(
            aio_pika.Channel.EXCHANGE_CLASS == InstrumentedExchange
        )
        self.assertFalse(aio_pika.Channel.QUEUE_CLASS == InstrumentedQueue)
        self.assertFalse(
            aio_pika.RobustChannel.EXCHANGE_CLASS == RobustInstrumentedExchange
        )
        self.assertFalse(
            aio_pika.RobustChannel.QUEUE_CLASS == RobustInstrumentedQueue
        )
