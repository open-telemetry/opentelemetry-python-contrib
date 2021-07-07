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
from unittest import mock

import aioredis

from opentelemetry.instrumentation.aioredis import AioRedisInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


class TestRedis(TestBase):
    async def test_span_properties(self):
        async def run():
            redis_client = aioredis.Redis("redis://localhost")
            AioRedisInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )

            with mock.patch.object(
                redis_client,
                "_pool_or_conn",
                new=mock.AsyncMock(return_value=""),
            ):
                await redis_client.get("key")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]
            self.assertEqual(span.name, "GET")
            self.assertEqual(span.kind, SpanKind.CLIENT)

        asyncio.get_event_loop().run_until_complete(run())

    def test_not_recording(self):
        async def run():
            redis_client = aioredis.Redis("")
            AioRedisInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )

            mock_tracer = mock.Mock()
            mock_span = mock.Mock()
            mock_span.is_recording.return_value = False
            mock_tracer.start_span.return_value = mock_span
            with mock.patch("opentelemetry.trace.get_tracer") as tracer:
                with mock.patch.object(
                    redis_client, "_pool_or_conn", new_callable=mock.AsyncMock
                ):
                    tracer.return_value = mock_tracer
                    await redis_client.get("key")
                    self.assertFalse(mock_span.is_recording())
                    self.assertTrue(mock_span.is_recording.called)
                    self.assertFalse(mock_span.set_attribute.called)
                    self.assertFalse(mock_span.set_status.called)

        asyncio.get_event_loop().run_until_complete(run())

    def test_instrument_uninstrument(self):
        async def run():
            redis_client = aioredis.Redis("")
            AioRedisInstrumentor().instrument(
                tracer_provider=self.tracer_provider
            )

            with mock.patch.object(
                redis_client, "_pool_or_conn", new_callable=mock.AsyncMock
            ):
                await redis_client.get("key")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            self.memory_exporter.clear()

            # Test uninstrument
            AioRedisInstrumentor().uninstrument()

            with mock.patch.object(
                redis_client, "_pool_or_conn", new_callable=mock.AsyncMock
            ):
                await redis_client.get("key")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)
            self.memory_exporter.clear()

            # Test instrument again
            AioRedisInstrumentor().instrument()

            with mock.patch.object(
                redis_client, "_pool_or_conn", new_callable=mock.AsyncMock
            ):
                await redis_client.get("key")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

        asyncio.get_event_loop().run_until_complete(run())
