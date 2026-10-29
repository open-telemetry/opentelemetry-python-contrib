# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
from unittest import TestCase, mock, skipIf
from unittest.mock import MagicMock

from aio_pika import Exchange, RobustExchange

from opentelemetry.instrumentation.aio_pika.publish_decorator import (
    PublishDecorator,
)
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
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
    CONNECTION_7,
    CONNECTION_8,
    CORRELATION_ID,
    EXCHANGE_NAME,
    MESSAGE,
    MESSAGE_ID,
    MESSAGING_SYSTEM_VALUE,
    ROUTING_KEY,
    SERVER_HOST,
    SERVER_PORT,
)


@skipIf(AIOPIKA_VERSION_INFO >= (8, 0), "Only for aio_pika 7")
class TestInstrumentedExchangeAioRmq7(TestCase):
    EXPECTED_ATTRIBUTES = {
        MESSAGING_SYSTEM: MESSAGING_SYSTEM_VALUE,
        SpanAttributes.MESSAGING_DESTINATION: f"{EXCHANGE_NAME},{ROUTING_KEY}",
        NET_PEER_NAME: SERVER_HOST,
        NET_PEER_PORT: SERVER_PORT,
        MESSAGING_MESSAGE_ID: MESSAGE_ID,
        SpanAttributes.MESSAGING_CONVERSATION_ID: CORRELATION_ID,
        SpanAttributes.MESSAGING_TEMP_DESTINATION: True,
    }

    def setUp(self):
        self.tracer = get_tracer(__name__)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def test_get_publish_span(self):
        exchange = Exchange(CONNECTION_7, CHANNEL_7, EXCHANGE_NAME)
        tracer = mock.MagicMock()
        PublishDecorator(tracer, exchange)._get_publish_span(MESSAGE, ROUTING_KEY)
        tracer.start_span.assert_called_once_with(
            f"{EXCHANGE_NAME},{ROUTING_KEY} send",
            kind=SpanKind.PRODUCER,
            attributes=self.EXPECTED_ATTRIBUTES,
        )

    def _test_publish(self, exchange_type: type[Exchange]):
        exchange = exchange_type(CONNECTION_7, CHANNEL_7, EXCHANGE_NAME)
        with mock.patch.object(PublishDecorator, "_get_publish_span") as mock_get_publish_span:
            with mock.patch.object(Exchange, "publish") as mock_publish:
                decorated_publish = PublishDecorator(self.tracer, exchange).decorate(mock_publish)
                self.loop.run_until_complete(decorated_publish(MESSAGE, ROUTING_KEY))
        mock_publish.assert_called_once()
        mock_get_publish_span.assert_called_once()

    def test_publish(self):
        self._test_publish(Exchange)

    def test_robust_publish(self):
        self._test_publish(RobustExchange)

    def _test_publish_works_with_not_recording_span(self, exchange_type):
        exchange = exchange_type(CONNECTION_7, CHANNEL_7, EXCHANGE_NAME)
        with mock.patch.object(PublishDecorator, "_get_publish_span") as mock_get_publish_span:
            mocked_not_recording_span = MagicMock()
            mocked_not_recording_span.is_recording.return_value = False
            mock_get_publish_span.return_value = mocked_not_recording_span
            with mock.patch.object(Exchange, "publish") as mock_publish:
                with mock.patch(
                    "opentelemetry.instrumentation.aio_pika.publish_decorator.propagate.inject"
                ) as mock_inject:
                    decorated_publish = PublishDecorator(self.tracer, exchange).decorate(mock_publish)
                    self.loop.run_until_complete(decorated_publish(MESSAGE, ROUTING_KEY))
        mock_publish.assert_called_once()
        mock_get_publish_span.assert_called_once()
        mock_inject.assert_called_once()

    def test_publish_works_with_not_recording_span(self):
        self._test_publish_works_with_not_recording_span(Exchange)

    def test_publish_works_with_not_recording_span_robust(self):
        self._test_publish_works_with_not_recording_span(RobustExchange)


@skipIf(AIOPIKA_VERSION_INFO <= (8, 0), "Only for aio_pika 8")
class TestInstrumentedExchangeAioRmq8(TestCase):
    EXPECTED_ATTRIBUTES = {
        MESSAGING_SYSTEM: MESSAGING_SYSTEM_VALUE,
        SpanAttributes.MESSAGING_DESTINATION: f"{EXCHANGE_NAME},{ROUTING_KEY}",
        NET_PEER_NAME: SERVER_HOST,
        NET_PEER_PORT: SERVER_PORT,
        MESSAGING_MESSAGE_ID: MESSAGE_ID,
        SpanAttributes.MESSAGING_CONVERSATION_ID: CORRELATION_ID,
        SpanAttributes.MESSAGING_TEMP_DESTINATION: True,
    }

    def setUp(self):
        self.tracer = get_tracer(__name__)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def test_get_publish_span(self):
        exchange = Exchange(CHANNEL_8, EXCHANGE_NAME)
        tracer = mock.MagicMock()
        PublishDecorator(tracer, exchange)._get_publish_span(MESSAGE, ROUTING_KEY)
        tracer.start_span.assert_called_once_with(
            f"{EXCHANGE_NAME},{ROUTING_KEY} send",
            kind=SpanKind.PRODUCER,
            attributes=self.EXPECTED_ATTRIBUTES,
        )

    def _test_publish(self, exchange_type: type[Exchange]):
        exchange = exchange_type(CONNECTION_8, CHANNEL_8, EXCHANGE_NAME)
        with mock.patch.object(PublishDecorator, "_get_publish_span") as mock_get_publish_span:
            with mock.patch.object(Exchange, "publish") as mock_publish:
                decorated_publish = PublishDecorator(self.tracer, exchange).decorate(mock_publish)
                self.loop.run_until_complete(decorated_publish(MESSAGE, ROUTING_KEY))
        mock_publish.assert_called_once()
        mock_get_publish_span.assert_called_once()

    def test_publish(self):
        self._test_publish(Exchange)

    def test_robust_publish(self):
        self._test_publish(RobustExchange)

    def _test_publish_works_with_not_recording_span(self, exchange_type):
        exchange = exchange_type(CONNECTION_7, CHANNEL_7, EXCHANGE_NAME)
        with mock.patch.object(PublishDecorator, "_get_publish_span") as mock_get_publish_span:
            mocked_not_recording_span = MagicMock()
            mocked_not_recording_span.is_recording.return_value = False
            mock_get_publish_span.return_value = mocked_not_recording_span
            with mock.patch.object(Exchange, "publish") as mock_publish:
                with mock.patch(
                    "opentelemetry.instrumentation.aio_pika.publish_decorator.propagate.inject"
                ) as mock_inject:
                    decorated_publish = PublishDecorator(self.tracer, exchange).decorate(mock_publish)
                    self.loop.run_until_complete(decorated_publish(MESSAGE, ROUTING_KEY))
        mock_publish.assert_called_once()
        mock_get_publish_span.assert_called_once()
        mock_inject.assert_called_once()

    def test_publish_works_with_not_recording_span(self):
        self._test_publish_works_with_not_recording_span(Exchange)

    def test_publish_works_with_not_recording_span_robust(self):
        self._test_publish_works_with_not_recording_span(RobustExchange)


class TestPublishErrorType(TestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        connection = CONNECTION_8 if AIOPIKA_VERSION_INFO >= (8, 0) else CONNECTION_7
        channel = CHANNEL_8 if AIOPIKA_VERSION_INFO >= (8, 0) else CHANNEL_7
        self.exchange = Exchange(connection, channel, EXCHANGE_NAME)
        patcher = mock.patch.object(
            PublishDecorator,
            "_get_publish_span",
            side_effect=lambda *_args: self.tracer.start_span("send", kind=SpanKind.PRODUCER),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.loop.close()
        super().tearDown()

    def test_error_type_recorded_on_a_failed_publish(self):
        error = ConnectionError("broker unavailable")
        failing_publish = mock.AsyncMock(side_effect=error)
        decorated_publish = PublishDecorator(self.tracer, self.exchange).decorate(failing_publish)

        with self.assertRaises(ConnectionError) as raised:
            self.loop.run_until_complete(decorated_publish(MESSAGE, ROUTING_KEY))
        self.assertIs(raised.exception, error)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.PRODUCER)
        error_type = spans[0].attributes[ERROR_TYPE]
        self.assertEqual(error_type, "ConnectionError")
        self.assertIs(type(error_type), str)

    def test_no_error_type_on_a_successful_publish(self):
        decorated_publish = PublishDecorator(self.tracer, self.exchange).decorate(mock.AsyncMock())
        self.loop.run_until_complete(decorated_publish(MESSAGE, ROUTING_KEY))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertNotIn(ERROR_TYPE, spans[0].attributes)
