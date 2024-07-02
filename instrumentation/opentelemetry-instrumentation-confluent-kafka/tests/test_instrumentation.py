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
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase

from .utils import MockConsumer, MockedMessage, MockedProducer


class TestConfluentKafka(TestBase):
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

    def test_poll(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        mocked_messages = [
            MockedMessage("topic-10", 0, 0, []),
            MockedMessage("topic-20", 2, 4, []),
            MockedMessage("topic-30", 1, 3, []),
        ]
        expected_spans = [
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-10 process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 0,
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-10",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    SpanAttributes.MESSAGING_MESSAGE_ID: "topic-10.0.0",
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-20 process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 2,
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-20",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    SpanAttributes.MESSAGING_MESSAGE_ID: "topic-20.2.4",
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-30 process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 1,
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-30",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    SpanAttributes.MESSAGING_MESSAGE_ID: "topic-30.1.3",
                },
            },
            {"name": "recv", "attributes": {}},
        ]

        consumer = MockConsumer(
            mocked_messages,
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        self.memory_exporter.clear()
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.poll()
        consumer.poll()
        consumer.poll()
        consumer.poll()

        span_list = self.memory_exporter.get_finished_spans()
        self._compare_spans(span_list, expected_spans)

    def test_consume(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        mocked_messages = [
            MockedMessage("topic-1", 0, 0, []),
            MockedMessage("topic-1", 2, 1, []),
            MockedMessage("topic-1", 3, 2, []),
            MockedMessage("topic-2", 0, 0, []),
            MockedMessage("topic-3", 0, 3, []),
            MockedMessage("topic-2", 0, 1, []),
        ]
        expected_spans = [
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-1 process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-1",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-2 process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-2",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-3 process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-3",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                },
            },
            {"name": "recv", "attributes": {}},
        ]

        consumer = MockConsumer(
            mocked_messages,
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )

        self.memory_exporter.clear()
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.consume(3)
        consumer.consume(1)
        consumer.consume(2)
        consumer.consume(1)
        span_list = self.memory_exporter.get_finished_spans()
        self._compare_spans(span_list, expected_spans)

    def test_close(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        mocked_messages = [
            MockedMessage("topic-a", 0, 0, []),
        ]
        expected_spans = [
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-a process",
                "attributes": {
                    SpanAttributes.MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 0,
                    SpanAttributes.MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-a",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    SpanAttributes.MESSAGING_MESSAGE_ID: "topic-a.0.0",
                },
            },
        ]

        consumer = MockConsumer(
            mocked_messages,
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        self.memory_exporter.clear()
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.poll()
        consumer.close()

        span_list = self.memory_exporter.get_finished_spans()
        self._compare_spans(span_list, expected_spans)

    def _compare_spans(self, spans, expected_spans):
        self.assertEqual(len(spans), len(expected_spans))
        for span, expected_span in zip(spans, expected_spans):
            self.assertEqual(expected_span["name"], span.name)
            for attribute_key, expected_attribute_value in expected_span[
                "attributes"
            ].items():
                self.assertEqual(
                    expected_attribute_value, span.attributes[attribute_key]
                )

    def test_producer_poll(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        message_queue = []

        producer = MockedProducer(
            message_queue,
            {
                "bootstrap.servers": "localhost:29092",
            },
        )

        producer = instrumentation.instrument_producer(producer)
        producer.produce(topic="topic-1", key="key-1", value="value-1")
        msg = producer.poll()
        self.assertIsNotNone(msg)

    def test_producer_flush(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        message_queue = []

        producer = MockedProducer(
            message_queue,
            {
                "bootstrap.servers": "localhost:29092",
            },
        )

        producer = instrumentation.instrument_producer(producer)
        producer.produce(topic="topic-1", key="key-1", value="value-1")
        msg = producer.flush()
        self.assertIsNotNone(msg)
