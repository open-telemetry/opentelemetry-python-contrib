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
from typing import Type
from unittest import TestCase, mock

from aio_pika import Queue

from opentelemetry.instrumentation.aio_pika.instrumented_queue import (
    InstrumentedQueue,
    RobustInstrumentedQueue,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import NonRecordingSpan

from .consts import (
    CHANNEL,
    CONNECTION,
    CORRELATION_ID,
    EXCHANGE_NAME,
    MESSAGE,
    MESSAGE_ID,
    MESSAGING_SYSTEM,
    QUEUE_NAME,
    SERVER_HOST,
    SERVER_PORT,
)


class TestInstrumentedQueue(TestCase):
    EXPECTED_ATTRIBUTES = {
        SpanAttributes.MESSAGING_SYSTEM: MESSAGING_SYSTEM,
        SpanAttributes.MESSAGING_DESTINATION: EXCHANGE_NAME,
        SpanAttributes.NET_PEER_NAME: SERVER_HOST,
        SpanAttributes.NET_PEER_PORT: SERVER_PORT,
        SpanAttributes.MESSAGING_MESSAGE_ID: MESSAGE_ID,
        SpanAttributes.MESSAGING_CONVERSATION_ID: CORRELATION_ID,
    }

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def test_get_callback_span(self):
        queue = InstrumentedQueue(
            CHANNEL, QUEUE_NAME, False, False, False, None
        )
        with mock.patch.object(
            NonRecordingSpan, "is_recording", return_value=True
        ):
            with mock.patch.object(
                NonRecordingSpan, "set_attribute"
            ) as mock_set_attrubute:
                queue._get_callback_span(MESSAGE)
        for name, value in self.EXPECTED_ATTRIBUTES.items():
            mock_set_attrubute.assert_any_call(name, value)

    def test_decorate_callback(self):
        queue = InstrumentedQueue(
            CHANNEL, QUEUE_NAME, False, False, False, None
        )
        callback = mock.MagicMock(return_value=asyncio.sleep(0))
        with mock.patch.object(
            InstrumentedQueue, "_get_callback_span"
        ) as mocked_get_callback_span:
            decorated_callback = queue._decorate_callback(callback)
            self.loop.run_until_complete(decorated_callback(MESSAGE))
        mocked_get_callback_span.assert_called_once()
        callback.assert_called_once_with(MESSAGE)

    def _test_consume(self, queue_type: Type[InstrumentedQueue]):
        queue = queue_type(CHANNEL, QUEUE_NAME, False, False, False, None)
        callback = mock.MagicMock()
        CONNECTION.connected = asyncio.Event()
        CONNECTION.connected.set()
        with mock.patch.object(
            InstrumentedQueue, "_decorate_callback"
        ) as mocked_decorate_callback:
            with mock.patch.object(
                Queue, "consume", return_value=asyncio.sleep(0)
            ) as mocked_consume:
                self.loop.run_until_complete(queue.consume(callback))
        mocked_decorate_callback.assert_called_once_with(callback)
        mocked_consume.assert_called_once()

    def test_consume(self):
        self._test_consume(InstrumentedQueue)

    def test_robust_consume(self):
        self._test_consume(RobustInstrumentedQueue)
