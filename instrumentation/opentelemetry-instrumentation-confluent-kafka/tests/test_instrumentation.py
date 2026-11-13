# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=no-name-in-module,import-outside-toplevel,too-many-public-methods
import asyncio
from unittest import mock

from opentelemetry import trace
from opentelemetry.instrumentation.confluent_kafka import (
    AutoInstrumentedConsumer,
    AutoInstrumentedProducer,
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
    MessagingOperationTypeValues,
    MessagingSystemValues,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.test.samplertestutil import CapturingSampler
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

from .utils import MockConsumer, MockedMessage, MockedProducer


class TestConfluentKafka(TestBase):
    def _configure_sampler(self, sampler: CapturingSampler) -> None:
        self.tracer_provider, self.memory_exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(self.tracer_provider.shutdown)

    def test_produce_attributes_passed_to_sampler(self) -> None:
        sampler = CapturingSampler()
        self._configure_sampler(sampler)
        producer = ConfluentKafkaInstrumentor().instrument_producer(
            MockedProducer([], {"bootstrap.servers": "broker-a:9092,broker-b:9093"}),
            tracer_provider=self.tracer_provider,
        )

        producer.produce("topic-1", value="value-1")

        expected = {
            MESSAGING_SYSTEM: MessagingSystemValues.KAFKA.value,
            SpanAttributes.MESSAGING_DESTINATION: "topic-1",
            SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
            MESSAGING_OPERATION: MessagingOperationTypeValues.PUBLISH.value,
            SERVER_ADDRESS: "broker-a",
            SERVER_PORT: 9092,
        }
        self.assertEqual(sampler.kind, SpanKind.PRODUCER)
        self.assertEqual(sampler.attributes, expected)
        for key, value in expected.items():
            self.assertIs(type(sampler.attributes[key]), type(value))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes, expected)

    def test_consumer_attributes_passed_to_sampler(self) -> None:
        for method in ("poll", "consume"):
            with self.subTest(method=method):
                sampler = CapturingSampler()
                self._configure_sampler(sampler)
                consumer = ConfluentKafkaInstrumentor().instrument_consumer(
                    MockConsumer(
                        [MockedMessage("topic-1", 0, 0, [])],
                        {"bootstrap.servers": "broker-a:9092", "group.id": "group-1"},
                    ),
                    tracer_provider=self.tracer_provider,
                )
                self.addCleanup(consumer.close)

                with mock.patch.object(sampler, "should_sample", wraps=sampler.should_sample) as should_sample:
                    getattr(consumer, method)()
                consumer.close()

                expected = {
                    MESSAGING_SYSTEM: MessagingSystemValues.KAFKA.value,
                    SpanAttributes.MESSAGING_DESTINATION: "topic-1",
                    SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                    MESSAGING_OPERATION: MessagingOperationTypeValues.PROCESS.value,
                    SERVER_ADDRESS: "broker-a",
                    SERVER_PORT: 9092,
                }
                if method == "poll":
                    expected[SpanAttributes.MESSAGING_KAFKA_PARTITION] = 0
                    expected[MESSAGING_MESSAGE_ID] = "topic-1.0.0"
                self.assertEqual(sampler.kind, SpanKind.CONSUMER)
                self.assertEqual(sampler.attributes, expected)
                for key, value in expected.items():
                    self.assertIs(type(sampler.attributes[key]), type(value))
                self.assertEqual(should_sample.call_count, 2)
                receive_attributes = {
                    **expected,
                    MESSAGING_OPERATION: MessagingOperationTypeValues.RECEIVE.value,
                }
                self.assertEqual(should_sample.call_args_list[0].args[3], SpanKind.CONSUMER)
                self.assertEqual(should_sample.call_args_list[0].args[4], receive_attributes)
                self.assertEqual(should_sample.call_args_list[1].args[4], expected)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 2)
                self.assertEqual(spans[0].name, "recv")
                self.assertEqual(spans[0].attributes, receive_attributes)
                self.assertEqual(spans[1].attributes, expected)

    def test_attributes_control_sampling(self) -> None:
        for method in ("produce", "poll", "consume"):
            for topic, expected_count in (("sample", 1), ("drop", 0)):
                with self.subTest(method=method, topic=topic):
                    sampler = CapturingSampler(required_attributes={SpanAttributes.MESSAGING_DESTINATION: "sample"})
                    self._configure_sampler(sampler)
                    if method == "produce":
                        messages = []
                        producer = ConfluentKafkaInstrumentor().instrument_producer(
                            MockedProducer(messages, {"bootstrap.servers": "localhost:9092"}),
                            tracer_provider=self.tracer_provider,
                        )
                        producer.produce(topic, value="value-1")
                        self.assertEqual(len(messages), 1)
                        self.assertEqual(messages[0].topic(), topic)
                    else:
                        record = MockedMessage(topic, 0, 0, [])
                        consumer = ConfluentKafkaInstrumentor().instrument_consumer(
                            MockConsumer([record], {"bootstrap.servers": "localhost:9092", "group.id": "group-1"}),
                            tracer_provider=self.tracer_provider,
                        )
                        self.addCleanup(consumer.close)
                        result = getattr(consumer, method)()
                        self.assertEqual(result, record if method == "poll" else [record])
                        consumer.close()
                    if method != "produce":
                        expected_count *= 2
                    self.assertEqual(len(self.memory_exporter.get_finished_spans()), expected_count)

    def test_library_errors_propagate(self) -> None:
        sampler = CapturingSampler()
        self._configure_sampler(sampler)
        for method in ("produce", "poll", "consume"):
            with self.subTest(method=method):
                if method == "produce":
                    original = MockedProducer([], {"bootstrap.servers": "localhost:9092"})
                    client = ConfluentKafkaInstrumentor().instrument_producer(
                        original, tracer_provider=self.tracer_provider
                    )
                    args = ("topic-1",)
                else:
                    original = MockConsumer([], {"bootstrap.servers": "localhost:9092", "group.id": "group-1"})
                    client = ConfluentKafkaInstrumentor().instrument_consumer(
                        original, tracer_provider=self.tracer_provider
                    )
                    self.addCleanup(client.close)
                    args = ()
                error = RuntimeError("test error")
                with mock.patch.object(original, method, side_effect=error):
                    with self.assertRaises(RuntimeError) as raised:
                        getattr(client, method)(*args)
                self.assertIs(raised.exception, error)

    def test_instrument_api(self) -> None:
        from confluent_kafka import Consumer, Producer  # noqa: PLC0415

        instrumentation = ConfluentKafkaInstrumentor()

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

        consumer = Consumer(
            **{
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            }
        )

        consumer = instrumentation.instrument_consumer(consumer)
        self.assertEqual(consumer.__class__, ProxiedConsumer)

        consumer = instrumentation.uninstrument_consumer(consumer)
        self.assertEqual(consumer.__class__, Consumer)

    def test_instrument_api_with_instrument(self) -> None:
        ConfluentKafkaInstrumentor().instrument()

        from confluent_kafka import Consumer, Producer  # noqa: PLC0415

        producer = Producer({"bootstrap.servers": "localhost:29092"})
        self.assertEqual(producer.__class__, AutoInstrumentedProducer)

        consumer = Consumer(
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            }
        )
        self.assertEqual(consumer.__class__, AutoInstrumentedConsumer)

        consumer = Consumer(
            **{
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            }
        )
        self.assertEqual(consumer.__class__, AutoInstrumentedConsumer)

        ConfluentKafkaInstrumentor().uninstrument()

    def test_consumer_commit_method_exists(self) -> None:
        from confluent_kafka import Consumer  # noqa: PLC0415

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
        self.assertGreaterEqual(carrier_dict.items(), {"key2": b"val2"}.items())

        carrier_list = [("key1", "val1")]
        context_setter.set(carrier_list, "key2", "val2")
        self.assertTrue(("key2", b"val2") in carrier_list)

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
        consumer.poll()  # empty poll — must not produce a span

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
        consumer.consume(1)  # empty consume — must not produce a span
        span_list = self.memory_exporter.get_finished_spans()
        self._compare_spans(span_list, expected_spans)

    def test_poll_empty_does_not_create_span(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [],
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

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

    def test_consume_empty_does_not_create_span(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [],
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        self.memory_exporter.clear()
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.consume(5)
        consumer.consume(5)

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

    def test_poll_empty_cleans_up_previous_span_and_token(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [MockedMessage("topic-1", 0, 0, [])],
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.poll()  # non-empty: sets _current_consume_span and _current_context_token
        self.assertIsNotNone(consumer._current_consume_span)
        self.assertIsNotNone(consumer._current_context_token)

        consumer.poll()  # empty: should clean up both
        self.assertIsNone(consumer._current_consume_span)
        self.assertIsNone(consumer._current_context_token)

    def test_consume_empty_cleans_up_previous_span_and_token(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [MockedMessage("topic-1", 0, 0, [])],
            {
                "bootstrap.servers": "localhost:29092",
                "group.id": "mygroup",
                "auto.offset.reset": "earliest",
            },
        )
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.consume(1)  # non-empty: sets _current_consume_span and _current_context_token
        self.assertIsNotNone(consumer._current_consume_span)
        self.assertIsNotNone(consumer._current_context_token)

        consumer.consume(1)  # empty: should clean up both
        self.assertIsNone(consumer._current_consume_span)
        self.assertIsNone(consumer._current_context_token)

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
            for attribute_key, expected_attribute_value in expected_span["attributes"].items():
                self.assertEqual(expected_attribute_value, span.attributes[attribute_key])

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

    def test_producer_sets_bootstrap_servers_attributes(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        producer = MockedProducer(
            [],
            {
                "bootstrap.servers": "broker-a:9092,broker-b:9093",
            },
        )

        producer = instrumentation.instrument_producer(producer)
        producer.produce(topic="topic-1", key="k", value="v")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes[SERVER_ADDRESS], "broker-a")
        self.assertEqual(span.attributes[SERVER_PORT], 9092)

    def test_consumer_sets_bootstrap_servers_attributes(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()
        consumer = MockConsumer(
            [MockedMessage("topic-1", 0, 0, [])],
            {
                "bootstrap.servers": "broker-1:9092",
                "group.id": "g",
                "auto.offset.reset": "earliest",
            },
        )

        self.memory_exporter.clear()
        consumer = instrumentation.instrument_consumer(consumer)
        consumer.poll()
        # Second (empty) poll ends the in-flight `<topic> process` span so it
        # shows up in the exporter.
        consumer.poll()

        process_span = next(s for s in self.memory_exporter.get_finished_spans() if s.name == "topic-1 process")
        self.assertEqual(process_span.attributes[SERVER_ADDRESS], "broker-1")
        self.assertEqual(process_span.attributes[SERVER_PORT], 9092)

    def test_aio_produce(self) -> None:
        from .utils import MockedAIOProducer  # noqa: PLC0415

        async def _run():
            instrumentation = ConfluentKafkaInstrumentor()
            tracer = self.tracer_provider.get_tracer(__name__)
            producer = MockedAIOProducer({"bootstrap.servers": "localhost:9092"})

            # Without headers: verify produce succeeds and headers kwarg is NOT forced
            # (confluent-kafka AIOProducer raises NotImplementedError if headers is passed)
            call_kwargs = {"topic": "test-topic", "value": b"test-value"}
            await instrumentation.wrap_aio_produce(
                producer.produce,
                producer,
                tracer,
                args=(),
                kwargs=call_kwargs,
            )
            self.assertNotIn("headers", call_kwargs)
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            self.assertEqual(spans[0].name, "test-topic send")

            # With headers: verify traceparent is injected into supplied headers
            self.memory_exporter.clear()
            supplied_headers = []
            await instrumentation.wrap_aio_produce(
                producer.produce,
                producer,
                tracer,
                args=(),
                kwargs={"topic": "test-topic", "value": b"test-value", "headers": supplied_headers},
            )
            self.assertTrue(any("traceparent" in str(h) for h in supplied_headers))

        asyncio.run(_run())

    def test_aio_poll(self) -> None:
        from .utils import MockedAIOConsumer  # noqa: PLC0415

        async def _run():
            instrumentation = ConfluentKafkaInstrumentor()
            tracer = self.tracer_provider.get_tracer(__name__)

            # MockedAIOConsumer dispatches the inner poll to a ThreadPoolExecutor,
            # matching the real AIOConsumer's behaviour.  This exercises the path
            # where the span is created on a worker thread and must be re-attached
            # to the caller's async-task context by wrap_aio_poll.
            queue = [MockedMessage("test-topic", 0, 0, [])]
            consumer = MockedAIOConsumer(
                queue,
                {"bootstrap.servers": "localhost:9092", "group.id": "g", "auto.offset.reset": "earliest"},
            )

            # Instrument the inner consumer's poll to simulate AutoInstrumentedConsumer.
            inner = consumer._consumer
            raw_poll = inner.poll

            def instrumented_inner_poll(timeout=None):
                return ConfluentKafkaInstrumentor.wrap_poll(raw_poll, inner, tracer, (timeout,), {})

            inner.poll = instrumented_inner_poll

            # First poll: inner Consumer creates a span on a worker thread;
            # wrap_aio_poll re-attaches it to the caller's async task context.
            msg = await instrumentation.wrap_aio_poll(
                consumer.poll,
                consumer,
                tracer,
                args=(),
                kwargs={},
            )
            self.assertIsNotNone(msg)

            # The span must now be current in the caller's async task.
            active_span = trace.get_current_span()
            self.assertTrue(active_span.is_recording())
            self.assertEqual(active_span.name, "test-topic process")

            # Verify worker thread context is not leaked to executor workers.
            loop = asyncio.get_running_loop()
            worker_span = await loop.run_in_executor(consumer._executor, trace.get_current_span)
            self.assertFalse(worker_span.is_recording())

            # Second (empty) poll detaches the previous context and ends the span.
            await instrumentation.wrap_aio_poll(
                consumer.poll,
                consumer,
                tracer,
                args=(),
                kwargs={},
            )

            spans = self.memory_exporter.get_finished_spans()
            process_spans = [s for s in spans if s.name == "test-topic process"]
            # Exactly one process span — no duplicates from the AIO wrapper layer.
            self.assertEqual(len(process_spans), 1)

            # Context detached in async task:
            self.assertFalse(trace.get_current_span().is_recording())

            await consumer.close()

        asyncio.run(_run())

    def test_aio_consume(self) -> None:
        from .utils import MockedAIOConsumer  # noqa: PLC0415

        async def _run():
            instrumentation = ConfluentKafkaInstrumentor()
            tracer = self.tracer_provider.get_tracer(__name__)

            queue = [
                MockedMessage("test-topic", 0, 0, []),
                MockedMessage("test-topic", 0, 1, []),
            ]
            consumer = MockedAIOConsumer(
                queue,
                {"bootstrap.servers": "localhost:9092", "group.id": "g", "auto.offset.reset": "earliest"},
            )

            inner = consumer._consumer
            raw_consume = inner.consume

            def instrumented_inner_consume(*args, **kwargs):
                return ConfluentKafkaInstrumentor.wrap_consume(raw_consume, inner, tracer, args, kwargs)

            inner.consume = instrumented_inner_consume

            # First batch consume
            msgs = await instrumentation.wrap_aio_consume(
                consumer.consume,
                consumer,
                tracer,
                args=(2,),
                kwargs={},
            )
            self.assertEqual(len(msgs), 2)

            # The span must now be current in the caller's async task.
            active_span = trace.get_current_span()
            self.assertTrue(active_span.is_recording())
            self.assertEqual(active_span.name, "test-topic process")

            # Subsequent empty consume ends the previous span and detaches context.
            await instrumentation.wrap_aio_consume(
                consumer.consume,
                consumer,
                tracer,
                args=(1,),
                kwargs={},
            )

            spans = self.memory_exporter.get_finished_spans()
            process_spans = [s for s in spans if s.name == "test-topic process"]
            self.assertEqual(len(process_spans), 1)

            # Context detached in async task:
            self.assertFalse(trace.get_current_span().is_recording())

            await consumer.close()

        asyncio.run(_run())

    def test_aio_config_kwargs(self) -> None:
        from opentelemetry.instrumentation.confluent_kafka import (  # noqa: PLC0415
            AutoInstrumentedAIOConsumer,
            AutoInstrumentedAIOProducer,
        )

        async def _run():
            instrumentor = ConfluentKafkaInstrumentor()
            instrumentor.instrument()
            try:
                if AutoInstrumentedAIOProducer is not None:
                    prod = AutoInstrumentedAIOProducer(producer_conf={"bootstrap.servers": "broker-p:9092"})
                    self.assertEqual(prod.config.get("bootstrap.servers"), "broker-p:9092")
                    await prod.close()

                if AutoInstrumentedAIOConsumer is not None:
                    cons = AutoInstrumentedAIOConsumer(
                        consumer_conf={"bootstrap.servers": "broker-c:9092", "group.id": "g"}
                    )
                    self.assertEqual(cons.config.get("bootstrap.servers"), "broker-c:9092")
                    inner = getattr(cons, "_consumer", None)
                    if inner is not None:
                        self.assertTrue(getattr(inner, "_is_aio", False))
                    await cons.close()
            finally:
                instrumentor.uninstrument()

        asyncio.run(_run())

    def test_aio_instrument_and_uninstrument(self) -> None:
        from opentelemetry.instrumentation.confluent_kafka import (  # noqa: PLC0415
            AutoInstrumentedAIOConsumer,
            AutoInstrumentedAIOProducer,
            _aio_module,
        )

        if _aio_module is None or AutoInstrumentedAIOProducer is None:
            return

        instrumentor = ConfluentKafkaInstrumentor()
        orig_producer = getattr(_aio_module, "AIOProducer", None)
        orig_consumer = getattr(_aio_module, "AIOConsumer", None)

        instrumentor.instrument()
        try:
            if orig_producer is not None:
                self.assertIs(_aio_module.AIOProducer, AutoInstrumentedAIOProducer)
            if orig_consumer is not None:
                self.assertIs(_aio_module.AIOConsumer, AutoInstrumentedAIOConsumer)
        finally:
            instrumentor.uninstrument()

        if orig_producer is not None:
            self.assertIs(_aio_module.AIOProducer, orig_producer)
        if orig_consumer is not None:
            self.assertIs(_aio_module.AIOConsumer, orig_consumer)
