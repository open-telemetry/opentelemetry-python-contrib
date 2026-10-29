# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
from unittest import TestCase, mock, skipIf

from aio_pika import Queue

from opentelemetry.instrumentation.aio_pika.callback_decorator import (
    CallbackDecorator,
)
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION,
    MESSAGING_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, get_tracer

from .consts import (
    AIOPIKA_VERSION_INFO,
    CHANNEL_7,
    CHANNEL_8,
    CORRELATION_ID,
    EXCHANGE_NAME,
    MESSAGE,
    MESSAGE_ID,
    MESSAGING_SYSTEM_VALUE,
    QUEUE_NAME,
    SERVER_HOST,
    SERVER_PORT,
)


@skipIf(AIOPIKA_VERSION_INFO >= (8, 0), "Only for aio_pika 7")
class TestInstrumentedQueueAioRmq7(TestCase):
    EXPECTED_ATTRIBUTES = {
        MESSAGING_SYSTEM: MESSAGING_SYSTEM_VALUE,
        SpanAttributes.MESSAGING_DESTINATION: EXCHANGE_NAME,
        NET_PEER_NAME: SERVER_HOST,
        NET_PEER_PORT: SERVER_PORT,
        MESSAGING_MESSAGE_ID: MESSAGE_ID,
        SpanAttributes.MESSAGING_CONVERSATION_ID: CORRELATION_ID,
        MESSAGING_OPERATION: "receive",
    }

    def setUp(self):
        self.tracer = get_tracer(__name__)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def test_get_callback_span(self):
        queue = Queue(CHANNEL_7, QUEUE_NAME, False, False, False, None)
        tracer = mock.MagicMock()
        CallbackDecorator(tracer, queue)._get_span(MESSAGE)
        tracer.start_span.assert_called_once_with(
            f"{EXCHANGE_NAME} receive",
            kind=SpanKind.CONSUMER,
            attributes=self.EXPECTED_ATTRIBUTES,
        )

    def test_decorate_callback(self):
        queue = Queue(CHANNEL_7, QUEUE_NAME, False, False, False, None)
        callback = mock.MagicMock(return_value=asyncio.sleep(0))
        with mock.patch.object(CallbackDecorator, "_get_span") as mocked_get_callback_span:
            callback_decorator = CallbackDecorator(self.tracer, queue)
            decorated_callback = callback_decorator.decorate(callback)
            self.loop.run_until_complete(decorated_callback(MESSAGE))
        mocked_get_callback_span.assert_called_once()
        callback.assert_called_once_with(MESSAGE)


@skipIf(AIOPIKA_VERSION_INFO <= (8, 0), "Only for aio_pika 8")
class TestInstrumentedQueueAioRmq8(TestCase):
    EXPECTED_ATTRIBUTES = {
        MESSAGING_SYSTEM: MESSAGING_SYSTEM_VALUE,
        SpanAttributes.MESSAGING_DESTINATION: EXCHANGE_NAME,
        NET_PEER_NAME: SERVER_HOST,
        NET_PEER_PORT: SERVER_PORT,
        MESSAGING_MESSAGE_ID: MESSAGE_ID,
        SpanAttributes.MESSAGING_CONVERSATION_ID: CORRELATION_ID,
        MESSAGING_OPERATION: "receive",
    }

    def setUp(self):
        self.tracer = get_tracer(__name__)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def test_get_callback_span(self):
        queue = Queue(CHANNEL_8, QUEUE_NAME, False, False, False, None)
        tracer = mock.MagicMock()
        CallbackDecorator(tracer, queue)._get_span(MESSAGE)
        tracer.start_span.assert_called_once_with(
            f"{EXCHANGE_NAME} receive",
            kind=SpanKind.CONSUMER,
            attributes=self.EXPECTED_ATTRIBUTES,
        )

    def test_decorate_callback(self):
        queue = Queue(CHANNEL_8, QUEUE_NAME, False, False, False, None)
        callback = mock.MagicMock(return_value=asyncio.sleep(0))
        with mock.patch.object(CallbackDecorator, "_get_span") as mocked_get_callback_span:
            callback_decorator = CallbackDecorator(self.tracer, queue)
            decorated_callback = callback_decorator.decorate(callback)
            self.loop.run_until_complete(decorated_callback(MESSAGE))
        mocked_get_callback_span.assert_called_once()
        callback.assert_called_once_with(MESSAGE)


class TestCallbackErrorType(TestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        channel = CHANNEL_8 if AIOPIKA_VERSION_INFO >= (8, 0) else CHANNEL_7
        self.queue = Queue(channel, QUEUE_NAME, False, False, False, None)
        patcher = mock.patch.object(
            CallbackDecorator,
            "_get_span",
            side_effect=lambda *_args: self.tracer.start_span("receive", kind=SpanKind.CONSUMER),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.loop.close()
        super().tearDown()

    def test_error_type_recorded_on_a_failed_callback(self):
        error = ValueError("cannot handle this message")
        failing_callback = mock.AsyncMock(side_effect=error)
        decorated_callback = CallbackDecorator(self.tracer, self.queue).decorate(failing_callback)

        with self.assertRaises(ValueError) as raised:
            self.loop.run_until_complete(decorated_callback(MESSAGE))
        self.assertIs(raised.exception, error)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.CONSUMER)
        error_type = spans[0].attributes[ERROR_TYPE]
        self.assertEqual(error_type, "ValueError")
        self.assertIs(type(error_type), str)

    def test_no_error_type_on_a_successful_callback(self):
        decorated_callback = CallbackDecorator(self.tracer, self.queue).decorate(mock.AsyncMock())
        self.loop.run_until_complete(decorated_callback(MESSAGE))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertNotIn(ERROR_TYPE, spans[0].attributes)
