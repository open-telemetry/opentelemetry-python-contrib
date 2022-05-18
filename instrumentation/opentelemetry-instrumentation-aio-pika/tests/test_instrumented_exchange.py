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
import asyncio
from argparse import Namespace
from typing import Type
from unittest import TestCase, mock

from aio_pika import Exchange
from yarl import URL

from opentelemetry.instrumentation.aio_pika.instrumented_exchange import (
    InstrumentedExchange,
    RobustInstrumentedExchange,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import NonRecordingSpan, Span

from .consts import (
    CHANNEL,
    CONNECTION,
    CORRELATION_ID,
    EXCHANGE_NAME,
    MESSAGE,
    MESSAGE_ID,
    MESSAGING_SYSTEM,
    ROUTING_KEY,
    SERVER_HOST,
    SERVER_PORT,
)


class TestInstrumentedExchange(TestCase):
    EXPECTED_ATTRIBUTES = {
        SpanAttributes.MESSAGING_SYSTEM: MESSAGING_SYSTEM,
        SpanAttributes.MESSAGING_DESTINATION: f"{EXCHANGE_NAME},{ROUTING_KEY}",
        SpanAttributes.NET_PEER_NAME: SERVER_HOST,
        SpanAttributes.NET_PEER_PORT: SERVER_PORT,
        SpanAttributes.MESSAGING_MESSAGE_ID: MESSAGE_ID,
        SpanAttributes.MESSAGING_CONVERSATION_ID: CORRELATION_ID,
        SpanAttributes.MESSAGING_TEMP_DESTINATION: True,
    }

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def test_get_publish_span(self):
        exchange = InstrumentedExchange(CONNECTION, CHANNEL, EXCHANGE_NAME)
        with mock.patch.object(
            NonRecordingSpan, "is_recording", return_value=True
        ):
            with mock.patch.object(
                NonRecordingSpan, "set_attribute"
            ) as mock_set_attrubute:
                exchange._get_publish_span(MESSAGE, ROUTING_KEY)
        for name, value in self.EXPECTED_ATTRIBUTES.items():
            mock_set_attrubute.assert_any_call(name, value)

    def _test_publish(self, exchange_type: Type[InstrumentedExchange]):
        exchange = exchange_type(CONNECTION, CHANNEL, EXCHANGE_NAME)
        with mock.patch.object(
            InstrumentedExchange, "_get_publish_span"
        ) as mock_get_publish_span:
            with mock.patch.object(
                Exchange, "publish", return_value=asyncio.sleep(0)
            ) as mock_publish:
                self.loop.run_until_complete(
                    exchange.publish(MESSAGE, ROUTING_KEY)
                )
        mock_publish.assert_called_once()
        mock_get_publish_span.assert_called_once()

    def test_publish(self):
        self._test_publish(InstrumentedExchange)

    def test_robust_publish(self):
        self._test_publish(RobustInstrumentedExchange)
