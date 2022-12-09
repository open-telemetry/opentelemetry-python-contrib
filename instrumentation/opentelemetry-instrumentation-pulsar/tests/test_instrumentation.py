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
from unittest import mock

import pulsar
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase

from opentelemetry.instrumentation.pulsar import (
    PulsarInstrumentor,
    _InstrumentedClient,
    _InstrumentedConsumer,
    _InstrumentedMessage,
    _InstrumentedProducer,
    wrap_message_listener,
)

PARTITION_KEY = "123"
SAMPLE_MESSAGE_ID = b"\x08\xef/\x10\x00"
TEST_TOPIC = "topic"


class TestPulsar(TestBase):
    def setUp(self):
        super().setUp()
        self.pulsar_instrumentation = PulsarInstrumentor()
        self.pulsar_instrumentation.instrument()

    def tearDown(self):
        self.pulsar_instrumentation.uninstrument()

    def test_pulsar_api(self):
        """This test mocks the underlying client instance, the native one and do not change
        anything on the exposed api."""

        client, _ = self._get_client()

        producer = client.create_producer(TEST_TOPIC)
        producer.send(b"hello", partition_key=PARTITION_KEY)
        consumer = client.subscribe(TEST_TOPIC, "subscription_name")
        message = consumer.receive()
        consumer.receive()

        consumer.acknowledge(message)
        consumer.negative_acknowledge(message)
        consumer.acknowledge_cumulative(message)
        consumer.close()
        spans = self.get_finished_spans()
        assert len(spans) == 2
        send, receive = spans
        self.assertSendSpan(send)

        assert (
                send.get_span_context().span_id
                != receive.get_span_context().span_id
        )
        assert (
                send.get_span_context().trace_id
                == receive.get_span_context().trace_id
        )

    def assertSendSpan(self, send, callback=None):
        # As they split the attributes, we need to check on each part as send_async only has more info later than send.
        operation = "send" if not callback else "send_async"
        callback = callback or send
        self.assertSpanHasAttributes(
            send,
            {
                SpanAttributes.MESSAGING_KAFKA_MESSAGE_KEY: "123",
                SpanAttributes.MESSAGING_DESTINATION_KIND: MessagingDestinationKindValues.QUEUE.value,
                SpanAttributes.MESSAGING_SYSTEM: "pulsar",
                SpanAttributes.MESSAGING_DESTINATION: TEST_TOPIC,
            },
        )
        self.assertSpanHasAttributes(
            callback, {SpanAttributes.MESSAGING_KAFKA_PARTITION: -1}
        )
        assert send.name == f"{operation} {TEST_TOPIC}"

    def test_pulsar_async_api(self):
        """This test mocks the underlying client instance, the native one and do not change
        anything on the exposed api."""
        client, stored_message = self._get_client()
        producer = client.create_producer(TEST_TOPIC)

        def send_callback(_res, _message_id):
            pass

        producer.send_async(
            b"hello", send_callback, partition_key=PARTITION_KEY
        )
        assert isinstance(stored_message.sent_message, pulsar.Message)
        wrapped_send_callback = producer._wrap_send_async_callback(
            send_callback, stored_message.sent_message.properties()
        )
        wrapped_send_callback(None, stored_message.sent_message.message_id())

        message = None

        def _message_listener(_consumer, _message):
            nonlocal message
            message = _message

        _message_listener = wrap_message_listener(
            TEST_TOPIC, self.pulsar_instrumentation._tracer, _message_listener
        )
        consumer = client.subscribe(
            TEST_TOPIC, "subscription_name", message_listener=_message_listener
        )
        _message_listener(consumer, stored_message.sent_message)

        consumer.acknowledge(message)
        consumer.negative_acknowledge(message)
        consumer.acknowledge_cumulative(message)
        consumer.close()

        spans = self.get_finished_spans()
        assert len(spans) == 3
        send, callback, receive = spans
        assert (
                send.get_span_context().span_id
                != receive.get_span_context().span_id
        )
        assert (
                send.get_span_context().trace_id
                == receive.get_span_context().trace_id
        )

        self.assertSendSpan(send, callback)

    def test_instrument_api(self) -> None:
        from pulsar import Client, Consumer, Message, Producer

        client = Client("pulsar+ssl://localhost")

        self.assertEqual(client.__class__, _InstrumentedClient)
        producer = Producer()

        self.assertEqual(producer.__class__, _InstrumentedProducer)

        consumer = Consumer()
        self.assertEqual(consumer.__class__, _InstrumentedConsumer)

        message = Message()
        self.assertEqual(message.__class__, _InstrumentedMessage)

    @mock.patch("pulsar.Client.__init__", autospec=True)
    def _get_client(self, mocked_init):
        class StoredMessage:
            sent_message = None

        stored_message = StoredMessage()

        def _send(message, *_args, **_kwargs):
            stored_message.sent_message = pulsar.Message._wrap(message)
            return b"\x08\xef/\x10\x00"

        def _receive(*_args, **_kwargs):
            assert stored_message.sent_message is not None
            return stored_message.sent_message

        def _send_async(_message, *_args, **_kwargs):
            stored_message.sent_message = pulsar.Message._wrap(_message)

        client_mock = mock.Mock()

        producer_mock = mock.Mock()
        producer_mock.send.side_effect = _send
        producer_mock.send_async.side_effect = _send_async
        producer_mock.topic.return_value = TEST_TOPIC

        consumer_mock = mock.Mock()
        consumer_mock.receive.side_effect = _receive

        def init(inner_self, *args, **kwargs):
            inner_self._client = client_mock
            inner_self._client.create_producer.return_value = producer_mock
            inner_self._client.subscribe.return_value = consumer_mock
            inner_self._consumers = []

        mocked_init.side_effect = init
        client = pulsar.Client("a")
        # This is only required because the message listener wrapping depends on our extended init
        client._set_tracer(self.pulsar_instrumentation._tracer)
        return client, stored_message
