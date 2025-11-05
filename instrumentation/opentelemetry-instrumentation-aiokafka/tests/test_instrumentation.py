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

from __future__ import annotations

import uuid
from typing import Any, Sequence, cast
from unittest import IsolatedAsyncioTestCase, TestCase, mock

import aiokafka
from aiokafka import (
    AIOKafkaConsumer,
    AIOKafkaProducer,
    ConsumerRecord,
    TopicPartition,
)
from wrapt import BoundFunctionWrapper

from opentelemetry import baggage, context
from opentelemetry.instrumentation.aiokafka import AIOKafkaInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, format_trace_id, set_span_in_context


class TestAIOKafkaInstrumentor(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = AIOKafkaInstrumentor()

        instrumentation.instrument()
        self.assertTrue(
            isinstance(AIOKafkaProducer.send, BoundFunctionWrapper)
        )
        self.assertTrue(
            isinstance(AIOKafkaConsumer.getone, BoundFunctionWrapper)
        )
        self.assertTrue(
            isinstance(AIOKafkaConsumer.getmany, BoundFunctionWrapper)
        )

        instrumentation.uninstrument()
        self.assertFalse(
            isinstance(AIOKafkaProducer.send, BoundFunctionWrapper)
        )
        self.assertFalse(
            isinstance(AIOKafkaConsumer.getone, BoundFunctionWrapper)
        )
        self.assertFalse(
            isinstance(AIOKafkaConsumer.getmany, BoundFunctionWrapper)
        )


class TestAIOKafkaInstrumentation(TestBase, IsolatedAsyncioTestCase):
    @staticmethod
    def consumer_record_factory(
        number: int, headers: tuple[tuple[str, bytes], ...]
    ) -> ConsumerRecord:
        return ConsumerRecord(
            f"topic_{number}",
            number,
            number,
            number,
            number,
            f"key_{number}".encode(),
            f"value_{number}".encode(),
            None,
            number,
            number,
            headers=headers,
        )

    @staticmethod
    def consumer_batch_factory(
        *headers: tuple[tuple[str, bytes], ...],
    ) -> dict[aiokafka.TopicPartition, list[aiokafka.ConsumerRecord]]:
        records = {}
        for number, record_headers in enumerate(headers, start=1):
            records[
                aiokafka.TopicPartition(
                    topic=f"topic_{number}", partition=number
                )
            ] = [
                ConsumerRecord(
                    f"topic_{number}",
                    number,
                    number,
                    number,
                    number,
                    f"key_{number}".encode(),
                    f"value_{number}".encode(),
                    None,
                    number,
                    number,
                    headers=record_headers,
                )
            ]

        return records

    @staticmethod
    async def consumer_factory(**consumer_kwargs: Any) -> AIOKafkaConsumer:
        consumer = AIOKafkaConsumer(**consumer_kwargs)

        consumer._client.bootstrap = mock.AsyncMock()
        consumer._client._wait_on_metadata = mock.AsyncMock()

        await consumer.start()

        consumer._fetcher.next_record = mock.AsyncMock()
        consumer._fetcher.fetched_records = mock.AsyncMock()

        return consumer

    @staticmethod
    async def producer_factory() -> AIOKafkaProducer:
        producer = AIOKafkaProducer(api_version="1.0")

        producer.client._wait_on_metadata = mock.AsyncMock()
        producer.client.bootstrap = mock.AsyncMock()
        producer._message_accumulator.add_message = mock.AsyncMock()
        producer._sender.start = mock.AsyncMock()
        producer._partition = mock.Mock(return_value=1)

        await producer.start()

        return producer

    def setUp(self):
        super().setUp()
        AIOKafkaInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self):
        super().tearDown()
        AIOKafkaInstrumentor().uninstrument()

    async def test_getone(self) -> None:
        client_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        consumer = await self.consumer_factory(
            client_id=client_id, group_id=group_id
        )
        self.addAsyncCleanup(consumer.stop)
        next_record_mock = cast(mock.AsyncMock, consumer._fetcher.next_record)

        expected_spans = [
            {
                "name": "topic_1 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_DESTINATION_NAME: "topic_1",
                    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID: "1",
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY: "key_1",
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET: 1,
                    messaging_attributes.MESSAGING_MESSAGE_ID: "topic_1.1.1",
                },
            },
            {
                "name": "topic_2 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_DESTINATION_NAME: "topic_2",
                    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID: "2",
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY: "key_2",
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET: 2,
                    messaging_attributes.MESSAGING_MESSAGE_ID: "topic_2.2.2",
                },
            },
        ]
        self.memory_exporter.clear()

        next_record_mock.side_effect = [
            self.consumer_record_factory(
                1,
                headers=(
                    (
                        "traceparent",
                        b"00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01",
                    ),
                ),
            ),
            self.consumer_record_factory(2, headers=()),
        ]

        await consumer.getone()
        next_record_mock.assert_awaited_with(())

        first_span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(
            format_trace_id(first_span.get_span_context().trace_id),
            "03afa25236b8cd948fa853d67038ac79",
        )

        await consumer.getone()
        next_record_mock.assert_awaited_with(())

        span_list = self.memory_exporter.get_finished_spans()
        self._compare_spans(span_list, expected_spans)

    async def test_getone_baggage(self) -> None:
        received_baggage = None

        async def async_consume_hook(span, *_) -> None:
            nonlocal received_baggage
            received_baggage = baggage.get_all(set_span_in_context(span))

        AIOKafkaInstrumentor().uninstrument()
        AIOKafkaInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            async_consume_hook=async_consume_hook,
        )

        consumer = await self.consumer_factory()
        self.addAsyncCleanup(consumer.stop)
        next_record_mock = cast(mock.AsyncMock, consumer._fetcher.next_record)

        self.memory_exporter.clear()

        next_record_mock.side_effect = [
            self.consumer_record_factory(
                1,
                headers=(
                    (
                        "traceparent",
                        b"00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01",
                    ),
                    ("baggage", b"foo=bar"),
                ),
            ),
        ]

        await consumer.getone()
        next_record_mock.assert_awaited_with(())

        self.assertEqual(received_baggage, {"foo": "bar"})

    async def test_getone_consume_hook(self) -> None:
        async_consume_hook_mock = mock.AsyncMock()

        def is_async_consume_hook_mock(obj: Any) -> bool:
            return obj is async_consume_hook_mock

        AIOKafkaInstrumentor().uninstrument()

        # mock.patch is a hack for Python 3.9 see https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3880
        with mock.patch(
            "opentelemetry.instrumentation.aiokafka.iscoroutinefunction"
        ) as iscoro:
            iscoro.side_effect = is_async_consume_hook_mock

            AIOKafkaInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                async_consume_hook=async_consume_hook_mock,
            )

        consumer = await self.consumer_factory()
        self.addAsyncCleanup(consumer.stop)
        next_record_mock = cast(mock.AsyncMock, consumer._fetcher.next_record)

        next_record_mock.side_effect = [
            self.consumer_record_factory(1, headers=())
        ]

        await consumer.getone()

        async_consume_hook_mock.assert_awaited_once()

    async def test_getmany(self) -> None:
        client_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        consumer = await self.consumer_factory(
            client_id=client_id, group_id=group_id
        )
        self.addAsyncCleanup(consumer.stop)
        fetched_records_mock = cast(
            mock.AsyncMock, consumer._fetcher.fetched_records
        )

        expected_spans = [
            {
                "name": "topic_1 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_DESTINATION_NAME: "topic_1",
                    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID: "1",
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY: "key_1",
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET: 1,
                    messaging_attributes.MESSAGING_MESSAGE_ID: "topic_1.1.1",
                },
            },
            {
                "name": "topic_1 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_DESTINATION_NAME: "topic_1",
                    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID: "1",
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_BATCH_MESSAGE_COUNT: 1,
                },
            },
            {
                "name": "topic_2 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_DESTINATION_NAME: "topic_2",
                    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID: "2",
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY: "key_2",
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET: 2,
                    messaging_attributes.MESSAGING_MESSAGE_ID: "topic_2.2.2",
                },
            },
            {
                "name": "topic_2 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_DESTINATION_NAME: "topic_2",
                    messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID: "2",
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_BATCH_MESSAGE_COUNT: 1,
                },
            },
            {
                "name": "topic_1, topic_2 receive",
                "kind": SpanKind.CONSUMER,
                "attributes": {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
                    server_attributes.SERVER_ADDRESS: '"localhost"',
                    messaging_attributes.MESSAGING_CLIENT_ID: client_id,
                    messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME: group_id,
                    messaging_attributes.MESSAGING_OPERATION_NAME: "receive",
                    messaging_attributes.MESSAGING_OPERATION_TYPE: messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
                    messaging_attributes.MESSAGING_BATCH_MESSAGE_COUNT: 2,
                },
            },
        ]
        self.memory_exporter.clear()

        fetched_records_mock.side_effect = [
            self.consumer_batch_factory(
                (
                    (
                        "traceparent",
                        b"00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01",
                    ),
                ),
                (),
            ),
        ]

        await consumer.getmany()
        fetched_records_mock.assert_awaited_with((), 0.0, max_records=None)

        span_list = self.memory_exporter.get_finished_spans()
        self._compare_spans(span_list, expected_spans)

    async def test_send(self) -> None:
        producer = await self.producer_factory()
        self.addAsyncCleanup(producer.stop)
        add_message_mock = cast(
            mock.AsyncMock, producer._message_accumulator.add_message
        )

        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("test_span") as span:
            await producer.send("topic_1", b"value_1")

        add_message_mock.assert_awaited_with(
            TopicPartition(topic="topic_1", partition=1),
            None,
            b"value_1",
            40.0,
            timestamp_ms=None,
            headers=[("traceparent", mock.ANY)],
        )
        add_message_mock.call_args_list[0].kwargs["headers"][0][1].startswith(
            f"00-{format_trace_id(span.get_span_context().trace_id)}-".encode()
        )

        await producer.send("topic_2", b"value_2")
        add_message_mock.assert_awaited_with(
            TopicPartition(topic="topic_2", partition=1),
            None,
            b"value_2",
            40.0,
            timestamp_ms=None,
            headers=[("traceparent", mock.ANY)],
        )

    async def test_send_baggage(self) -> None:
        producer = await self.producer_factory()
        self.addAsyncCleanup(producer.stop)
        add_message_mock = cast(
            mock.AsyncMock, producer._message_accumulator.add_message
        )

        tracer = self.tracer_provider.get_tracer(__name__)
        ctx = baggage.set_baggage("foo", "bar")
        context.attach(ctx)

        with tracer.start_as_current_span("test_span", context=ctx):
            await producer.send("topic_1", b"value_1")

        add_message_mock.assert_awaited_with(
            TopicPartition(topic="topic_1", partition=1),
            None,
            b"value_1",
            40.0,
            timestamp_ms=None,
            headers=[("traceparent", mock.ANY), ("baggage", b"foo=bar")],
        )

    async def test_send_produce_hook(self) -> None:
        async_produce_hook_mock = mock.AsyncMock()

        def is_async_produce_hook_mock(obj: Any) -> bool:
            return obj is async_produce_hook_mock

        AIOKafkaInstrumentor().uninstrument()
        # mock.patch is a hack for Python 3.9 see https://github.com/open-telemetry/opentelemetry-python-contrib/pull/3880
        with mock.patch(
            "opentelemetry.instrumentation.aiokafka.iscoroutinefunction"
        ) as iscoro:
            iscoro.side_effect = is_async_produce_hook_mock

            AIOKafkaInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                async_produce_hook=async_produce_hook_mock,
            )

        producer = await self.producer_factory()
        self.addAsyncCleanup(producer.stop)

        await producer.send("topic_1", b"value_1")

        async_produce_hook_mock.assert_awaited_once()

    def _compare_spans(
        self, spans: Sequence[ReadableSpan], expected_spans: list[dict]
    ) -> None:
        self.assertEqual(len(spans), len(expected_spans))
        for span, expected_span in zip(spans, expected_spans):
            self.assertEqual(expected_span["name"], span.name, msg=span.name)
            self.assertEqual(expected_span["kind"], span.kind, msg=span.name)
            self.assertEqual(
                expected_span["attributes"],
                dict(span.attributes),
                msg=span.name,
            )

    async def test_send_and_wait(self) -> None:
        AIOKafkaInstrumentor().uninstrument()
        AIOKafkaInstrumentor().instrument(tracer_provider=self.tracer_provider)

        producer = await self.producer_factory()
        add_message_mock: mock.AsyncMock = (
            producer._message_accumulator.add_message
        )
        add_message_mock.side_effect = [mock.AsyncMock()(), mock.AsyncMock()()]

        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("test_span") as span:
            await producer.send_and_wait("topic_1", b"value_1")

        add_message_mock.assert_awaited_with(
            TopicPartition(topic="topic_1", partition=1),
            None,
            b"value_1",
            40.0,
            timestamp_ms=None,
            headers=[("traceparent", mock.ANY)],
        )
        assert (
            add_message_mock.call_args_list[0]
            .kwargs["headers"][0][1]
            .startswith(
                f"00-{format_trace_id(span.get_span_context().trace_id)}-".encode()
            )
        )

        await producer.send_and_wait("topic_2", b"value_2")
        add_message_mock.assert_awaited_with(
            TopicPartition(topic="topic_2", partition=1),
            None,
            b"value_2",
            40.0,
            timestamp_ms=None,
            headers=[("traceparent", mock.ANY)],
        )
