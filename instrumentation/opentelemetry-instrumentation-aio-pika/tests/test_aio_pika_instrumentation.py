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
from unittest import TestCase, mock

import wrapt
from aio_pika import Exchange, Queue

from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor
from opentelemetry.instrumentation.aio_pika.package import (
    _instrumentation_name,
)
from opentelemetry.test.test_base import TestBase

from .consts import (
    AIOPIKA_VERSION_INFO,
    CHANNEL_7,
    CHANNEL_8,
    CONNECTION_7,
    EXCHANGE_NAME,
    MESSAGE,
    ROUTING_KEY,
)


class TestPika(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = AioPikaInstrumentor()
        instrumentation.instrument()
        self.assertTrue(isinstance(Queue.consume, wrapt.BoundFunctionWrapper))
        self.assertTrue(
            isinstance(Exchange.publish, wrapt.BoundFunctionWrapper)
        )
        instrumentation.uninstrument()
        self.assertFalse(isinstance(Queue.consume, wrapt.BoundFunctionWrapper))
        self.assertFalse(
            isinstance(Exchange.publish, wrapt.BoundFunctionWrapper)
        )


class TestInstrumentationScopeName(TestBase):
    """Test instrumentation scope via actual span output (not mocking internals)."""

    def setUp(self):
        super().setUp()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        with self.disable_logging():
            AioPikaInstrumentor().uninstrument()
        self.loop.close()
        super().tearDown()

    def test_instrumentation_scope_name(self):
        """Verify instrumentation scope via the real instrument() path."""
        async def _noop_publish(self, *args, **kwargs):
            return None

        with mock.patch.object(Exchange, "publish", new=_noop_publish):
            AioPikaInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )
            major = AIOPIKA_VERSION_INFO[0]
            if major == 7:
                exchange = Exchange(CONNECTION_7, CHANNEL_7, EXCHANGE_NAME)
            elif major == 8:
                exchange = Exchange(CHANNEL_8, EXCHANGE_NAME)
            else:
                self.fail(f"Unsupported aio-pika version: {AIOPIKA_VERSION_INFO}")
            self.loop.run_until_complete(
                exchange.publish(MESSAGE, ROUTING_KEY)
            )

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].instrumentation_scope.name, _instrumentation_name
        )
