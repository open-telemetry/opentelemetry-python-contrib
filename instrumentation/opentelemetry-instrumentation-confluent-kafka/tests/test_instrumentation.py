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
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION,
    MESSAGING_SYSTEM,
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

    def test_producer_proxy_implemented_all_methods(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()

        producer = Producer({"bootstrap.servers": "localhost:29092"})

        producer = instrumentation.instrument_producer(producer)

        self.assertEqual(producer.__class__, ProxiedProducer)
        self.assertTrue(hasattr(producer, "produce"))
        self.assertTrue(hasattr(producer, "poll"))
        self.assertTrue(hasattr(producer, "flush"))
        self.assertTrue(hasattr(producer, "init_transactions"))
        self.assertTrue(hasattr(producer, "begin_transaction"))
        self.assertTrue(hasattr(producer, "commit_transaction"))
        self.assertTrue(hasattr(producer, "abort_transaction"))
        self.assertTrue(hasattr(producer, "send_offsets_to_transaction"))
        self.assertTrue(hasattr(producer, "list_topics"))

    def test_consumer_proxy_implemented_all_methods(self) -> None:
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
        self.assertTrue(hasattr(consumer, "assign"))
        self.assertTrue(hasattr(consumer, "assignment"))
        self.assertTrue(hasattr(consumer, "close"))
        self.assertTrue(hasattr(consumer, "committed"))
        self.assertTrue(hasattr(consumer, "consume"))
        self.assertTrue(hasattr(consumer, "consumer_group_metadata"))
        self.assertTrue(hasattr(consumer, "get_watermark_offsets"))
        self.assertTrue(hasattr(consumer, "incremental_assign"))
        self.assertTrue(hasattr(consumer, "incremental_unassign"))
        self.assertTrue(hasattr(consumer, "list_topics"))
        self.assertTrue(hasattr(consumer, "offsets_for_times"))
        self.assertTrue(hasattr(consumer, "pause"))
        self.assertTrue(hasattr(consumer, "poll"))
        self.assertTrue(hasattr(consumer, "position"))
        self.assertTrue(hasattr(consumer, "resume"))
        self.assertTrue(hasattr(consumer, "seek"))
        self.assertTrue(hasattr(consumer, "store_offsets"))
        self.assertTrue(hasattr(consumer, "subscribe"))
        self.assertTrue(hasattr(consumer, "unassign"))
        self.assertTrue(hasattr(consumer, "unsubscribe"))

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
                    MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 0,
                    MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-10",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    MESSAGING_MESSAGE_ID: "topic-10.0.0",
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-20 process",
                "attributes": {
                    MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 2,
                    MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-20",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    MESSAGING_MESSAGE_ID: "topic-20.2.4",
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-30 process",
                "attributes": {
                    MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 1,
                    MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-30",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    MESSAGING_MESSAGE_ID: "topic-30.1.3",
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
                    MESSAGING_OPERATION: "process",
                    MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-1",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-2 process",
                "attributes": {
                    MESSAGING_OPERATION: "process",
                    MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-2",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                },
            },
            {"name": "recv", "attributes": {}},
            {
                "name": "topic-3 process",
                "attributes": {
                    MESSAGING_OPERATION: "process",
                    MESSAGING_SYSTEM: "kafka",
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
                    MESSAGING_OPERATION: "process",
                    SpanAttributes.MESSAGING_KAFKA_PARTITION: 0,
                    MESSAGING_SYSTEM: "kafka",
                    SpanAttributes.MESSAGING_DESTINATION: "topic-a",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    MESSAGING_MESSAGE_ID: "topic-a.0.0",
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

    def _assert_topic(self, span, expected_topic: str) -> None:
        self.assertEqual(
            span.attributes[SpanAttributes.MESSAGING_DESTINATION],
            expected_topic,
        )

    def _assert_span_count(self, span_list, expected_count: int) -> None:
        self.assertEqual(len(span_list), expected_count)

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
        span_list = self.memory_exporter.get_finished_spans()
        self._assert_span_count(span_list, 1)
        self._assert_topic(span_list[0], "topic-1")

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
        span_list = self.memory_exporter.get_finished_spans()
        self._assert_span_count(span_list, 1)
        self._assert_topic(span_list[0], "topic-1")
