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

from tortoise import Tortoise, fields, models

from opentelemetry import trace
from opentelemetry.instrumentation.tortoiseorm import TortoiseORMInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.test.test_base import TestBase


class MockModel(models.Model):
    id = fields.IntField(pk=True)
    name = fields.TextField()

    def __str__(self):
        return self.name


class TestTortoiseORMInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        TortoiseORMInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        TortoiseORMInstrumentor().uninstrument()
        self._async_call(Tortoise._drop_databases())

    # pylint: disable-next=no-self-use
    def _async_call(self, coro):
        return asyncio.run(coro)

    # pylint: disable-next=no-self-use
    async def _init_tortoise(self):
        await Tortoise.init(
            db_url="sqlite://:memory:",
            modules={"models": [__name__]},
        )
        await Tortoise.generate_schemas()

    def test_trace_integration(self):
        async def run():
            await self._init_tortoise()
            await MockModel.create(name="Test 1")
            await MockModel.filter(name="Test 1").first()

        self._async_call(run())
        spans = self.memory_exporter.get_finished_spans()

        crud_spans = [s for s in spans if s.name in ("INSERT", "SELECT")]
        self.assertGreaterEqual(len(crud_spans), 2)

        insert_span = next(s for s in crud_spans if s.name == "INSERT")
        self.assertEqual(insert_span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(insert_span.attributes[DB_SYSTEM], "sqlite")
        self.assertEqual(insert_span.attributes[DB_NAME], ":memory:")
        self.assertIn("INSERT", insert_span.attributes[DB_STATEMENT])

        select_span = next(s for s in crud_spans if s.name == "SELECT")
        self.assertEqual(select_span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(select_span.attributes[DB_SYSTEM], "sqlite")
        self.assertEqual(select_span.attributes[DB_NAME], ":memory:")
        self.assertIn("SELECT", select_span.attributes[DB_STATEMENT])

    def test_capture_parameters(self):
        TortoiseORMInstrumentor().uninstrument()
        TortoiseORMInstrumentor().instrument(capture_parameters=True)

        async def run():
            await self._init_tortoise()
            await MockModel.create(name="Test Parameterized")

        self._async_call(run())
        spans = self.memory_exporter.get_finished_spans()
        insert_span = next(s for s in spans if s.name == "INSERT")
        self.assertIn("db.statement.parameters", insert_span.attributes)
        self.assertIn(
            "Test Parameterized",
            insert_span.attributes["db.statement.parameters"],
        )

    def test_uninstrument(self):
        TortoiseORMInstrumentor().uninstrument()

        async def run():
            await self._init_tortoise()
            await MockModel.create(name="Test Uninstrumented")

        self._async_call(run())
        spans = self.memory_exporter.get_finished_spans()
        crud_spans = [s for s in spans if s.name in ("INSERT", "SELECT")]
        self.assertEqual(len(crud_spans), 0)

    def test_suppress_instrumentation(self):
        async def run():
            await self._init_tortoise()
            with suppress_instrumentation():
                await MockModel.create(name="Test Suppressed")

        self._async_call(run())
        spans = self.memory_exporter.get_finished_spans()
        crud_spans = [s for s in spans if s.name in ("INSERT", "SELECT")]
        self.assertEqual(len(crud_spans), 0)

    def test_no_op_tracer_provider(self):
        TortoiseORMInstrumentor().uninstrument()
        TortoiseORMInstrumentor().instrument(
            tracer_provider=trace.NoOpTracerProvider()
        )

        async def run():
            await self._init_tortoise()
            await MockModel.create(name="Test NoOp")

        self._async_call(run())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
