# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import contextlib
from unittest import mock

from tortoise import Tortoise, fields, models

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.tortoiseorm import TortoiseORMInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.test.test_base import TestBase


class MockModel(models.Model):
    id = fields.IntField(pk=True)
    name = fields.TextField()

    def __str__(self):
        return self.name


@contextlib.contextmanager
def use_semconv_opt_in(sem_conv_mode):
    """Context manager to set OTEL_SEMCONV_STABILITY_OPT_IN and reset state."""
    env_patch = mock.patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode},
    )
    _OpenTelemetrySemanticConventionStability._initialized = False
    env_patch.start()
    try:
        yield
    finally:
        env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False


class TestTortoiseORMInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False
        TortoiseORMInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        TortoiseORMInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
        if Tortoise._inited:
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
        """Default mode (no opt-in): old semconv attributes only."""

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
        # Old attrs present
        self.assertEqual(insert_span.attributes[DB_SYSTEM], "sqlite")
        self.assertEqual(insert_span.attributes[DB_NAME], ":memory:")
        self.assertIn("INSERT", insert_span.attributes[DB_STATEMENT])
        # New attrs must NOT be present in default mode
        self.assertNotIn(DB_SYSTEM_NAME, insert_span.attributes)
        self.assertNotIn(DB_NAMESPACE, insert_span.attributes)
        self.assertNotIn(DB_QUERY_TEXT, insert_span.attributes)

        select_span = next(s for s in crud_spans if s.name == "SELECT")
        self.assertEqual(select_span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(select_span.attributes[DB_SYSTEM], "sqlite")
        self.assertEqual(select_span.attributes[DB_NAME], ":memory:")
        self.assertIn("SELECT", select_span.attributes[DB_STATEMENT])

    def test_trace_integration_new_semconv(self):
        """database opt-in mode: new stable semconv attributes only."""
        TortoiseORMInstrumentor().uninstrument()

        with use_semconv_opt_in("database"):
            TortoiseORMInstrumentor().instrument()

            async def run():
                await self._init_tortoise()
                await MockModel.create(name="Test New Semconv")
                await MockModel.filter(name="Test New Semconv").first()

            self._async_call(run())

        spans = self.memory_exporter.get_finished_spans()
        crud_spans = [s for s in spans if s.name in ("INSERT", "SELECT")]
        self.assertGreaterEqual(len(crud_spans), 2)

        insert_span = next(s for s in crud_spans if s.name == "INSERT")
        # New attrs present
        self.assertEqual(insert_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertEqual(insert_span.attributes[DB_NAMESPACE], ":memory:")
        self.assertIn("INSERT", insert_span.attributes[DB_QUERY_TEXT])
        # Old attrs must NOT be present
        self.assertNotIn(DB_SYSTEM, insert_span.attributes)
        self.assertNotIn(DB_NAME, insert_span.attributes)
        self.assertNotIn(DB_STATEMENT, insert_span.attributes)

        select_span = next(s for s in crud_spans if s.name == "SELECT")
        self.assertEqual(select_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertIn("SELECT", select_span.attributes[DB_QUERY_TEXT])

    def test_trace_integration_dup_semconv(self):
        """database/dup mode: both old and new semconv attributes present."""
        TortoiseORMInstrumentor().uninstrument()

        with use_semconv_opt_in("database/dup"):
            TortoiseORMInstrumentor().instrument()

            async def run():
                await self._init_tortoise()
                await MockModel.create(name="Test Dup Semconv")

            self._async_call(run())

        spans = self.memory_exporter.get_finished_spans()
        insert_span = next((s for s in spans if s.name == "INSERT"), None)
        self.assertIsNotNone(insert_span)

        # Old attrs present
        self.assertIn(DB_SYSTEM, insert_span.attributes)
        self.assertIn(DB_NAME, insert_span.attributes)
        self.assertIn(DB_STATEMENT, insert_span.attributes)
        # New attrs also present
        self.assertIn(DB_SYSTEM_NAME, insert_span.attributes)
        self.assertIn(DB_NAMESPACE, insert_span.attributes)
        self.assertIn(DB_QUERY_TEXT, insert_span.attributes)
        # Values are consistent
        self.assertEqual(insert_span.attributes[DB_SYSTEM], "sqlite")
        self.assertEqual(insert_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertEqual(insert_span.attributes[DB_NAME], ":memory:")
        self.assertEqual(insert_span.attributes[DB_NAMESPACE], ":memory:")

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
