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

# pylint: disable=no-name-in-module,import-outside-toplevel

from unittest import TestCase

from opentelemetry.instrumentation.pulsar import (
    InstrumentedClient,
    InstrumentedConsumer,
    InstrumentedMessage,
    InstrumentedProducer,
    PulsarInstrumentor,
)


class TestPulsar(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = PulsarInstrumentor()
        instrumentation.instrument()

        from pulsar import Client, Consumer, Message, Producer

        client = Client("pulsar+ssl://localhost")

        self.assertEqual(client.__class__, InstrumentedClient)
        producer = Producer()

        self.assertEqual(producer.__class__, InstrumentedProducer)

        consumer = Consumer()
        self.assertEqual(consumer.__class__, InstrumentedConsumer)

        message = Message()
        self.assertEqual(message.__class__, InstrumentedMessage)
