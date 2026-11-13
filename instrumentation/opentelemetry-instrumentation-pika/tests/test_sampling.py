# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from collections import deque
from types import SimpleNamespace
from typing import Any
from unittest import mock

from pika.adapters.blocking_connection import _ConsumerDeliveryEvt
from pika.spec import Basic, BasicProperties

from opentelemetry import context
from opentelemetry.instrumentation.pika import utils
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.trace import MessagingOperationValues, SpanAttributes
from opentelemetry.test.samplertestutil import CapturingSampler
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


class TestPikaSampling(TestBase):
    def _configure_sampler(self, sampler: CapturingSampler) -> None:
        self.tracer_provider, self.memory_exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(self.tracer_provider.shutdown)
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.channel = SimpleNamespace(connection=SimpleNamespace(params=SimpleNamespace(host="localhost", port=5672)))

    def _invoke(self, operation: str, callback: mock.Mock, properties: BasicProperties) -> Any:
        if operation == "publish":
            decorated = utils._decorate_basic_publish(callback, self.channel, self.tracer)
            return decorated("exchange", "queue", b"body", properties)
        method = Basic.Deliver(exchange="exchange", routing_key="queue")
        if operation == "callback":
            decorated = utils._decorate_callback(callback, self.tracer, "task")
            return decorated(self.channel, method, properties, b"body")
        event = _ConsumerDeliveryEvt(method, properties, b"body")
        generator_info = SimpleNamespace(consumer_tag="consumer")
        proxy = utils.ReadyMessagesDequeProxy(deque([event]), generator_info, self.tracer, callback)
        try:
            return proxy.popleft()
        finally:
            if proxy._self_active_token:
                context.detach(proxy._self_active_token)

    def test_attributes_passed_to_sampler(self) -> None:
        for operation in ("publish", "callback", "generator"):
            with self.subTest(operation=operation):
                sampler = CapturingSampler()
                self._configure_sampler(sampler)
                properties = BasicProperties(headers={}, message_id="message-1", correlation_id="conversation-1")
                callback = mock.Mock()

                self._invoke(operation, callback, properties)

                expected = {
                    messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.RABBITMQ.value,
                    SpanAttributes.MESSAGING_DESTINATION: "exchange",
                    messaging_attributes.MESSAGING_MESSAGE_ID: "message-1",
                    SpanAttributes.MESSAGING_CONVERSATION_ID: "conversation-1",
                }
                if operation == "publish":
                    expected[SpanAttributes.MESSAGING_TEMP_DESTINATION] = True
                else:
                    expected[SpanAttributes.MESSAGING_OPERATION] = MessagingOperationValues.RECEIVE.value
                if operation != "generator":
                    expected[NET_PEER_NAME] = "localhost"
                    expected[NET_PEER_PORT] = 5672
                self.assertEqual(sampler.kind, SpanKind.PRODUCER if operation == "publish" else SpanKind.CONSUMER)
                self.assertEqual(sampler.attributes, expected)
                for key, value in expected.items():
                    self.assertIs(type(sampler.attributes[key]), type(value))
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].attributes, expected)
                callback.assert_called_once()

    def test_attributes_control_sampling(self) -> None:
        for operation in ("publish", "callback", "generator"):
            for message_id, expected_count in (("sample", 1), ("drop", 0)):
                with self.subTest(operation=operation, message_id=message_id):
                    sampler = CapturingSampler(
                        required_attributes={messaging_attributes.MESSAGING_MESSAGE_ID: "sample"}
                    )
                    self._configure_sampler(sampler)
                    properties = BasicProperties(headers={}, message_id=message_id)
                    callback = mock.Mock()

                    self._invoke(operation, callback, properties)

                    callback.assert_called_once()
                    self.assertEqual(len(self.memory_exporter.get_finished_spans()), expected_count)

    def test_errors_propagate(self) -> None:
        for operation in ("publish", "callback"):
            with self.subTest(operation=operation):
                self._configure_sampler(CapturingSampler())
                error = RuntimeError("test error")
                callback = mock.Mock(side_effect=error)
                properties = BasicProperties(headers={}, message_id="message-1")

                with self.assertRaises(RuntimeError) as raised:
                    self._invoke(operation, callback, properties)

                self.assertIs(raised.exception, error)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
                self.assertEqual(spans[0].attributes[messaging_attributes.MESSAGING_MESSAGE_ID], "message-1")
