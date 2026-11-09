# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, mock

from opentelemetry.instrumentation.aio_pika.callback_decorator import CallbackDecorator
from opentelemetry.instrumentation.aio_pika.publish_decorator import PublishDecorator
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION,
    MESSAGING_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import NET_PEER_NAME, NET_PEER_PORT
from opentelemetry.semconv.trace import MessagingOperationValues, SpanAttributes
from opentelemetry.test.samplertestutil import CapturingSampler
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode, get_current_span
from opentelemetry.util.types import AttributeValue


class TestAioPikaSampling(TestBase, IsolatedAsyncioTestCase):
    def _configure_sampler(self, sampler: CapturingSampler) -> None:
        self.tracer_provider, self.memory_exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(self.tracer_provider.shutdown)
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.channel = SimpleNamespace(connection=SimpleNamespace(url=SimpleNamespace(host="localhost", port=5672)))

    @staticmethod
    def _message(message_id: str = "message-1", exchange: str = "exchange") -> SimpleNamespace:
        headers = {}
        return SimpleNamespace(
            properties=SimpleNamespace(message_id=message_id, correlation_id="conversation-1", headers=headers),
            headers=headers,
            exchange=exchange,
            routing_key="queue",
        )

    async def _invoke(self, operation: str, callback: mock.AsyncMock, message: SimpleNamespace) -> object:
        if operation == "publish":
            exchange = SimpleNamespace(name="exchange", channel=self.channel)
            return await PublishDecorator(self.tracer, exchange).decorate(callback)(message, "queue")
        queue = SimpleNamespace(channel=self.channel)
        return await CallbackDecorator(self.tracer, queue).decorate(callback)(message)

    @staticmethod
    def _expected_attributes(operation: str, destination: str) -> dict[str, AttributeValue]:
        attributes: dict[str, AttributeValue] = {
            MESSAGING_SYSTEM: "rabbitmq",
            SpanAttributes.MESSAGING_DESTINATION: destination,
            MESSAGING_MESSAGE_ID: "message-1",
            SpanAttributes.MESSAGING_CONVERSATION_ID: "conversation-1",
            NET_PEER_NAME: "localhost",
            NET_PEER_PORT: 5672,
        }
        if operation == "publish":
            attributes[SpanAttributes.MESSAGING_TEMP_DESTINATION] = True
        else:
            attributes[MESSAGING_OPERATION] = MessagingOperationValues.RECEIVE.value
        return attributes

    async def test_publish_attributes_passed_to_sampler(self) -> None:
        sampler = CapturingSampler()
        self._configure_sampler(sampler)
        message = self._message()
        callback = mock.AsyncMock(return_value="published")

        result = await self._invoke("publish", callback, message)

        expected = self._expected_attributes("publish", "exchange,queue")
        self.assertEqual(result, "published")
        callback.assert_awaited_once_with(message, "queue")
        self.assertEqual(sampler.kind, SpanKind.PRODUCER)
        self.assertEqual(sampler.name, "exchange,queue send")
        self.assertEqual(sampler.attributes, expected)
        for key, value in expected.items():
            self.assertIs(type(sampler.attributes[key]), type(value))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes, expected)
        self.assertIn("traceparent", message.properties.headers)

    async def test_consumer_attributes_passed_to_sampler(self) -> None:
        for exchange, destination in (("exchange", "exchange"), ("", "queue")):
            with self.subTest(exchange=exchange):
                sampler = CapturingSampler()
                self._configure_sampler(sampler)
                message = self._message(exchange=exchange)
                message.headers["traceparent"] = "00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01"
                callback = mock.AsyncMock(return_value="processed")
                previous_span = get_current_span()

                result = await self._invoke("receive", callback, message)

                expected = self._expected_attributes("receive", destination)
                self.assertEqual(result, "processed")
                callback.assert_awaited_once_with(message)
                self.assertEqual(sampler.kind, SpanKind.CONSUMER)
                self.assertEqual(sampler.name, f"{destination} receive")
                self.assertEqual(sampler.attributes, expected)
                for key, value in expected.items():
                    self.assertIs(type(sampler.attributes[key]), type(value))
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].attributes, expected)
                self.assertEqual(spans[0].parent.span_id, 0x405FF022E8247C46)
                self.assertIs(get_current_span(), previous_span)

    async def test_attributes_control_sampling(self) -> None:
        for operation in ("publish", "receive"):
            for message_id, expected_count in (("sample", 1), ("drop", 0)):
                with self.subTest(operation=operation, message_id=message_id):
                    sampler = CapturingSampler(required_attributes={MESSAGING_MESSAGE_ID: "sample"})
                    self._configure_sampler(sampler)
                    message = self._message(message_id=message_id)
                    callback = mock.AsyncMock(return_value="result")

                    result = await self._invoke(operation, callback, message)

                    self.assertEqual(result, "result")
                    callback.assert_awaited_once()
                    self.assertEqual(len(self.memory_exporter.get_finished_spans()), expected_count)
                    if operation == "publish":
                        self.assertIn("traceparent", message.properties.headers)

    async def test_errors_propagate(self) -> None:
        for operation in ("publish", "receive"):
            with self.subTest(operation=operation):
                sampler = CapturingSampler()
                self._configure_sampler(sampler)
                message = self._message()
                error = RuntimeError("test error")
                callback = mock.AsyncMock(side_effect=error)
                previous_span = get_current_span()

                with self.assertRaises(RuntimeError) as raised:
                    await self._invoke(operation, callback, message)

                self.assertIs(raised.exception, error)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
                self.assertEqual(spans[0].attributes, sampler.attributes)
                self.assertIs(get_current_span(), previous_span)
