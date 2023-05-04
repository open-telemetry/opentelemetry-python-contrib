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

# pylint: disable=no-name-in-module

from unittest import TestCase

from confluent_kafka import Consumer, Producer

from opentelemetry.instrumentation.confluent_kafka import (
    ConfluentKafkaInstrumentor,
    ProxiedConsumer,
    ProxiedProducer,
)
from opentelemetry.instrumentation.confluent_kafka.utils import (
    KafkaContextGetter,
    KafkaContextSetter,
)


class TestConfluentKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()

        producer = Producer({"bootstrap.servers": "localhost:29092"})
        producer = instrumentation.instrument_producer(producer)

        self.assertEqual(producer.__class__, ProxiedProducer)

        producer = instrumentation.uninstrument_producer(producer)
        self.assertEqual(producer.__class__, Producer)

        producer = Producer({"bootstrap.servers": "localhost:29092"})
        producer = instrumentation.instrument_producer(producer)

        self.assertEqual(producer.__class__, ProxiedProducer)

        producer = instrumentation.uninstrument_producer(producer)
        self.assertEqual(producer.__class__, Producer)

        consumer = Consumer(
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            }
        )

        consumer = instrumentation.instrument_consumer(consumer)
        self.assertEqual(consumer.__class__, ProxiedConsumer)

        consumer = instrumentation.uninstrument_consumer(consumer)
        self.assertEqual(consumer.__class__, Consumer)

    def test_consumer_commit_method_exists(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()

        consumer = Consumer(
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            }
        )

        consumer = instrumentation.instrument_consumer(consumer)
        self.assertEqual(consumer.__class__, ProxiedConsumer)
        self.assertTrue(hasattr(consumer, "commit"))

    def test_context_setter(self) -> None:
        context_setter = KafkaContextSetter()

        carrier_dict = {"key1": "val1"}
        context_setter.set(carrier_dict, "key2", "val2")
        self.assertGreaterEqual(
            carrier_dict.items(), {"key2": "val2".encode()}.items()
        )

        carrier_list = [("key1", "val1")]
        context_setter.set(carrier_list, "key2", "val2")
        self.assertTrue(("key2", "val2".encode()) in carrier_list)

    def test_context_getter(self) -> None:
        context_setter = KafkaContextSetter()
        context_getter = KafkaContextGetter()

        carrier_dict = {}
        context_setter.set(carrier_dict, "key1", "val1")
        self.assertEqual(context_getter.get(carrier_dict, "key1"), ["val1"])
        self.assertEqual(["key1"], context_getter.keys(carrier_dict))

        carrier_list = []
        context_setter.set(carrier_list, "key1", "val1")
        self.assertEqual(context_getter.get(carrier_list, "key1"), ["val1"])
        self.assertEqual(["key1"], context_getter.keys(carrier_list))
