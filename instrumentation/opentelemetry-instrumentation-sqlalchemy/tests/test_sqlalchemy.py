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
import logging
from unittest import mock

import pytest
import sqlalchemy
from sqlalchemy import (
    create_engine,
    text,
)

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.sqlalchemy import (
    EngineTracer,
    SQLAlchemyInstrumentor,
)
from opentelemetry.instrumentation.sqlalchemy.engine import (
    _get_db_name_from_cursor,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.test.test_base import TestBase


class TestSqlalchemyInstrumentation(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog  # pylint: disable=attribute-defined-outside-init

    def setUp(self):
        super().setUp()
        # Reset semconv state before each test for reproducibility
        # Tests using @mock.patch.dict will re-initialize again after the mock is applied
        _OpenTelemetrySemanticConventionStability._initialized = False

    def tearDown(self):
        super().tearDown()
        SQLAlchemyInstrumentor().uninstrument()

    def test_trace_integration(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        cnx.execute(text("/* leading comment */ SELECT	1 + 1;")).fetchall()
        cnx.execute(
            text(
                "/* leading comment */ SELECT	1 + 1; /* trailing comment */"
            )
        ).fetchall()
        cnx.execute(text("SELECT	1 + 1; /* trailing comment */")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 5)
        # first span - the connection to the db
        self.assertEqual(spans[0].name, "connect")
        self.assertEqual(spans[0].kind, trace.SpanKind.CLIENT)
        # second span - the query itself
        self.assertEqual(spans[1].name, "SELECT :memory:")
        self.assertEqual(spans[1].kind, trace.SpanKind.CLIENT)
        # spans for queries with comments
        self.assertEqual(spans[2].name, "SELECT :memory:")
        self.assertEqual(spans[2].kind, trace.SpanKind.CLIENT)
        self.assertEqual(spans[3].name, "SELECT :memory:")
        self.assertEqual(spans[3].kind, trace.SpanKind.CLIENT)
        self.assertEqual(spans[4].name, "SELECT :memory:")
        self.assertEqual(spans[4].kind, trace.SpanKind.CLIENT)

    def test_instrument_two_engines(self):
        engine_1 = create_engine("sqlite:///:memory:")
        engine_2 = create_engine("sqlite:///:memory:")

        SQLAlchemyInstrumentor().instrument(
            engines=[engine_1, engine_2],
            tracer_provider=self.tracer_provider,
        )

        cnx_1 = engine_1.connect()
        cnx_1.execute(text("SELECT	1 + 1;")).fetchall()
        cnx_2 = engine_2.connect()
        cnx_2.execute(text("SELECT	1 + 1;")).fetchall()

        spans = self.memory_exporter.get_finished_spans()
        # 2 queries + 2 engine connect
        self.assertEqual(len(spans), 4)

    def test_instrument_engine_connect(self):
        engine = create_engine("sqlite:///:memory:")

        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )

        engine.connect()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_async_trace_integration(self):
        async def run():
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            SQLAlchemyInstrumentor().instrument(
                engine=engine.sync_engine, tracer_provider=self.tracer_provider
            )
            async with engine.connect() as cnx:
                await cnx.execute(text("SELECT	1 + 1;"))
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)
            # first span - the connection to the db
            self.assertEqual(spans[0].name, "connect")
            self.assertEqual(spans[0].kind, trace.SpanKind.CLIENT)
            # second span - the query
            self.assertEqual(spans[1].name, "SELECT :memory:")
            self.assertEqual(spans[1].kind, trace.SpanKind.CLIENT)
            self.assertEqual(
                spans[1].instrumentation_scope.name,
                "opentelemetry.instrumentation.sqlalchemy",
            )

        asyncio.get_event_loop().run_until_complete(run())

    def test_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_context = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_context.__enter__ = mock.Mock(return_value=mock_span)
        mock_context.__exit__ = mock.Mock(return_value=None)
        mock_tracer.start_span.return_value = mock_context
        mock_tracer.start_as_current_span.return_value = mock_context
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            engine = create_engine("sqlite:///:memory:")
            SQLAlchemyInstrumentor().instrument(
                engine=engine,
                tracer_provider=self.tracer_provider,
            )
            cnx = engine.connect()
            cnx.execute(text("SELECT	1 + 1;")).fetchall()
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    def test_create_engine_wrapper(self):
        SQLAlchemyInstrumentor().instrument()
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 2)
        # first span - the connection to the db
        self.assertEqual(spans[0].name, "connect")
        self.assertEqual(spans[0].attributes[DB_NAME], ":memory:")
        self.assertEqual(spans[0].attributes[DB_SYSTEM], "sqlite")
        self.assertEqual(spans[0].kind, trace.SpanKind.CLIENT)
        # second span - the query
        self.assertEqual(spans[1].name, "SELECT :memory:")
        self.assertEqual(spans[1].kind, trace.SpanKind.CLIENT)
        self.assertEqual(
            spans[1].instrumentation_scope.name,
            "opentelemetry.instrumentation.sqlalchemy",
        )

    def test_instrument_engine_from_config(self):
        SQLAlchemyInstrumentor().instrument()
        from sqlalchemy import (  # noqa: PLC0415
            engine_from_config,  # pylint: disable-all
        )

        engine = engine_from_config({"sqlalchemy.url": "sqlite:///:memory:"})
        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 2)

    def test_create_engine_wrapper_enable_commenter(self):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        SQLAlchemyInstrumentor().instrument(
            enable_commenter=True,
            commenter_options={"db_framework": False},
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        # sqlcommenter
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[DB_STATEMENT],
            "SELECT  1;",
        )

    def test_create_engine_wrapper_enable_commenter_stmt_enabled(self):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        SQLAlchemyInstrumentor().instrument(
            enable_commenter=True,
            commenter_options={"db_framework": False},
            enable_attribute_commenter=True,
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        # sqlcommenter
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertRegex(
            query_span.attributes[DB_STATEMENT],
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_create_engine_wrapper_enable_commenter_otel_values_false(self):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        SQLAlchemyInstrumentor().instrument(
            enable_commenter=True,
            commenter_options={
                "db_framework": False,
                "opentelemetry_values": False,
            },
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        # sqlcommenter
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[DB_STATEMENT],
            "SELECT  1;",
        )

    def test_create_engine_wrapper_enable_commenter_stmt_enabled_otel_values_false(
        self,
    ):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        SQLAlchemyInstrumentor().instrument(
            enable_commenter=True,
            commenter_options={
                "db_framework": False,
                "opentelemetry_values": False,
            },
            enable_attribute_commenter=True,
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        # sqlcommenter
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertRegex(
            query_span.attributes[DB_STATEMENT],
            r"SELECT  1 /\*db_driver='(.*)'\*/;",
        )

    def test_custom_tracer_provider(self):
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": "test",
                    "deployment.environment": "env",
                    "service.version": "1234",
                },
            ),
        )
        provider.add_span_processor(
            export.SimpleSpanProcessor(self.memory_exporter)
        )

        SQLAlchemyInstrumentor().instrument(tracer_provider=provider)
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0].resource.attributes["service.name"], "test")
        self.assertEqual(
            spans[0].resource.attributes["deployment.environment"], "env"
        )
        self.assertEqual(
            spans[0].resource.attributes["service.version"], "1234"
        )

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_create_async_engine_wrapper(self):
        async def run():
            SQLAlchemyInstrumentor().instrument()
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.connect() as cnx:
                await cnx.execute(text("SELECT	1 + 1;"))
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)
            # first span - the connection to the db
            self.assertEqual(spans[0].name, "connect")
            self.assertEqual(spans[0].attributes[DB_NAME], ":memory:")
            self.assertEqual(spans[0].attributes[DB_SYSTEM], "sqlite")
            self.assertEqual(spans[0].kind, trace.SpanKind.CLIENT)
            # second span - the query
            self.assertEqual(spans[1].name, "SELECT :memory:")
            self.assertEqual(spans[1].kind, trace.SpanKind.CLIENT)
            self.assertEqual(
                spans[1].instrumentation_scope.name,
                "opentelemetry.instrumentation.sqlalchemy",
            )

        asyncio.get_event_loop().run_until_complete(run())

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_create_async_engine_wrapper_enable_commenter(self):
        async def run():
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
            SQLAlchemyInstrumentor().instrument(
                enable_commenter=True,
                commenter_options={
                    "db_framework": False,
                },
            )
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.connect() as cnx:
                await cnx.execute(text("SELECT  1;"))
            # sqlcommenter
            self.assertRegex(
                self.caplog.records[1].getMessage(),
                r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
            )
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)
            # first span is connection to db
            self.assertEqual(spans[0].name, "connect")
            # second span is query itself
            query_span = spans[1]
            self.assertEqual(
                query_span.attributes[DB_STATEMENT],
                "SELECT  1;",
            )

        asyncio.get_event_loop().run_until_complete(run())

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_create_async_engine_wrapper_enable_commenter_stmt_enabled(self):
        async def run():
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
            SQLAlchemyInstrumentor().instrument(
                enable_commenter=True,
                commenter_options={
                    "db_framework": False,
                },
                enable_attribute_commenter=True,
            )
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.connect() as cnx:
                await cnx.execute(text("SELECT  1;"))
            # sqlcommenter
            self.assertRegex(
                self.caplog.records[1].getMessage(),
                r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
            )
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)
            # first span is connection to db
            self.assertEqual(spans[0].name, "connect")
            # second span is query itself
            query_span = spans[1]
            self.assertRegex(
                query_span.attributes[DB_STATEMENT],
                r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
            )

        asyncio.get_event_loop().run_until_complete(run())

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_create_async_engine_wrapper_enable_commenter_otel_values_false(
        self,
    ):
        async def run():
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
            SQLAlchemyInstrumentor().instrument(
                enable_commenter=True,
                commenter_options={
                    "db_framework": False,
                    "opentelemetry_values": False,
                },
            )
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.connect() as cnx:
                await cnx.execute(text("SELECT  1;"))
            # sqlcommenter
            self.assertRegex(
                self.caplog.records[1].getMessage(),
                r"SELECT  1 /\*db_driver='(.*)'\*/;",
            )
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)
            # first span is connection to db
            self.assertEqual(spans[0].name, "connect")
            # second span is query itself
            query_span = spans[1]
            self.assertEqual(
                query_span.attributes[DB_STATEMENT],
                "SELECT  1;",
            )

        asyncio.get_event_loop().run_until_complete(run())

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_create_async_engine_wrapper_enable_commenter_stmt_enabled_otel_values_false(
        self,
    ):
        async def run():
            logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
            SQLAlchemyInstrumentor().instrument(
                enable_commenter=True,
                commenter_options={
                    "db_framework": False,
                    "opentelemetry_values": False,
                },
                enable_attribute_commenter=True,
            )
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.connect() as cnx:
                await cnx.execute(text("SELECT  1;"))
            # sqlcommenter
            self.assertRegex(
                self.caplog.records[1].getMessage(),
                r"SELECT  1 /\*db_driver='(.*)'\*/;",
            )
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)
            # first span is connection to db
            self.assertEqual(spans[0].name, "connect")
            # second span is query itself
            query_span = spans[1]
            self.assertRegex(
                query_span.attributes[DB_STATEMENT],
                r"SELECT  1 /\*db_driver='(.*)'*/;",
            )

        asyncio.get_event_loop().run_until_complete(run())

    def test_uninstrument(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 2)
        # first span - the connection to the db
        self.assertEqual(spans[0].name, "connect")
        self.assertEqual(spans[0].kind, trace.SpanKind.CLIENT)
        # second span - the query itself
        self.assertEqual(spans[1].name, "SELECT :memory:")
        self.assertEqual(spans[1].kind, trace.SpanKind.CLIENT)

        self.memory_exporter.clear()
        SQLAlchemyInstrumentor().uninstrument()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        engine2 = create_engine("sqlite:///:memory:")
        cnx2 = engine2.connect()
        cnx2.execute(text("SELECT	2 + 2;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

    def test_uninstrument_without_engine(self):
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider
        )
        from sqlalchemy import create_engine  # noqa: PLC0415

        engine = create_engine("sqlite:///:memory:")

        cnx = engine.connect()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        self.memory_exporter.clear()
        SQLAlchemyInstrumentor().uninstrument()
        cnx.execute(text("SELECT	1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_no_op_tracer_provider(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=trace.NoOpTracerProvider(),
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_no_memory_leakage_if_engine_diposed(self):
        SQLAlchemyInstrumentor().instrument()
        import gc  # noqa: PLC0415
        import weakref  # noqa: PLC0415

        from sqlalchemy import create_engine  # noqa: PLC0415

        from opentelemetry.instrumentation.sqlalchemy.engine import (  # noqa: PLC0415
            EngineTracer,
        )

        callback = mock.Mock()

        def make_shortlived_engine():
            engine = create_engine("sqlite:///:memory:")
            # Callback will be called if engine is deallocated during garbage
            # collection
            weakref.finalize(engine, callback)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 + 1;")).fetchall()

        for _ in range(0, 5):
            make_shortlived_engine()

        gc.collect()
        assert callback.call_count == 5
        assert len(EngineTracer._remove_event_listener_params) == 0

    def test_suppress_instrumentation_create_engine(self):
        SQLAlchemyInstrumentor().instrument()

        from sqlalchemy import create_engine  # noqa: PLC0415

        with suppress_instrumentation():
            engine = create_engine("sqlite:///:memory:")

        self.assertTrue(not isinstance(engine, EngineTracer))

    @pytest.mark.skipif(
        not sqlalchemy.__version__.startswith("1.4"),
        reason="only run async tests for 1.4",
    )
    def test_suppress_instrumentation_create_async_engine(self):
        async def run():
            SQLAlchemyInstrumentor().instrument()
            from sqlalchemy.ext.asyncio import (  # pylint: disable-all  # noqa: PLC0415
                create_async_engine,
            )

            with suppress_instrumentation():
                engine = create_async_engine("sqlite+aiosqlite:///:memory:")

            self.assertTrue(not isinstance(engine, EngineTracer))

        asyncio.get_event_loop().run_until_complete(run())

    def test_suppress_instrumentation_connect(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )

        with suppress_instrumentation():
            with engine.connect():
                pass

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_semconv_default_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        self.assertIn(DB_SYSTEM, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM], "sqlite")
        self.assertIn(DB_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAME], ":memory:")
        # Verify new conventions are NOT present
        self.assertNotIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertNotIn(DB_NAMESPACE, connect_span.attributes)

        query_span = spans[1]
        self.assertIn(DB_STATEMENT, query_span.attributes)
        self.assertIn(DB_SYSTEM, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM], "sqlite")
        # Verify new conventions are NOT present
        self.assertNotIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertNotIn(DB_SYSTEM_NAME, query_span.attributes)

    @mock.patch.dict("os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http"})
    def test_semconv_http_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        # HTTP attributes should use new semconv
        self.assertNotIn(NET_PEER_NAME, connect_span.attributes)
        # DB attributes should still use old semconv
        self.assertIn(DB_SYSTEM, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM], "sqlite")
        self.assertIn(DB_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAME], ":memory:")
        # Verify new DB conventions are NOT present
        self.assertNotIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertNotIn(DB_NAMESPACE, connect_span.attributes)

        query_span = spans[1]
        # DB attributes should still use old semconv
        self.assertIn(DB_STATEMENT, query_span.attributes)
        self.assertIn(DB_SYSTEM, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM], "sqlite")
        # Verify new DB conventions are NOT present
        self.assertNotIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertNotIn(DB_SYSTEM_NAME, query_span.attributes)

    @mock.patch.dict("os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "database"})
    def test_semconv_database_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        self.assertIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertIn(DB_NAMESPACE, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAMESPACE], ":memory:")
        # Verify old conventions are NOT present
        self.assertNotIn(DB_SYSTEM, connect_span.attributes)
        self.assertNotIn(DB_NAME, connect_span.attributes)

        query_span = spans[1]
        self.assertIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertIn(DB_SYSTEM_NAME, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM_NAME], "sqlite")
        # Verify old conventions are NOT present
        self.assertNotIn(DB_STATEMENT, query_span.attributes)
        self.assertNotIn(DB_SYSTEM, query_span.attributes)

    @mock.patch.dict(
        "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http,database"}
    )
    def test_semconv_http_and_database_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        # New DB conventions should be present
        self.assertIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertIn(DB_NAMESPACE, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAMESPACE], ":memory:")
        # Old DB conventions should NOT be present
        self.assertNotIn(DB_SYSTEM, connect_span.attributes)
        self.assertNotIn(DB_NAME, connect_span.attributes)

        query_span = spans[1]
        # New DB conventions should be present
        self.assertIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertIn(DB_SYSTEM_NAME, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM_NAME], "sqlite")
        # Old DB conventions should NOT be present
        self.assertNotIn(DB_STATEMENT, query_span.attributes)
        self.assertNotIn(DB_SYSTEM, query_span.attributes)

    @mock.patch.dict("os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http/dup"})
    def test_semconv_http_dup_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        # DB attributes should use old semconv only
        self.assertIn(DB_SYSTEM, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM], "sqlite")
        self.assertIn(DB_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAME], ":memory:")
        # Verify new DB conventions are NOT present
        self.assertNotIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertNotIn(DB_NAMESPACE, connect_span.attributes)

        query_span = spans[1]
        # DB attributes should use old semconv
        self.assertIn(DB_STATEMENT, query_span.attributes)
        self.assertIn(DB_SYSTEM, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM], "sqlite")
        # Verify new DB conventions are NOT present
        self.assertNotIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertNotIn(DB_SYSTEM_NAME, query_span.attributes)

    @mock.patch.dict(
        "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "database/dup"}
    )
    def test_semconv_database_dup_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        # Old conventions
        self.assertIn(DB_SYSTEM, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM], "sqlite")
        self.assertIn(DB_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAME], ":memory:")
        # New conventions
        self.assertIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertIn(DB_NAMESPACE, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAMESPACE], ":memory:")

        query_span = spans[1]
        # Old conventions
        self.assertIn(DB_STATEMENT, query_span.attributes)
        self.assertIn(DB_SYSTEM, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM], "sqlite")
        # New conventions
        self.assertIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertIn(DB_SYSTEM_NAME, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM_NAME], "sqlite")

    @mock.patch.dict(
        "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http/dup,database/dup"}
    )
    def test_semconv_http_and_database_dup_mode(self):
        SQLAlchemyInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1 + 1;")).fetchall()
        spans = self.memory_exporter.get_finished_spans()

        connect_span = spans[0]
        # Both old and new DB conventions
        self.assertIn(DB_SYSTEM, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM], "sqlite")
        self.assertIn(DB_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAME], ":memory:")
        self.assertIn(DB_SYSTEM_NAME, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_SYSTEM_NAME], "sqlite")
        self.assertIn(DB_NAMESPACE, connect_span.attributes)
        self.assertEqual(connect_span.attributes[DB_NAMESPACE], ":memory:")

        query_span = spans[1]
        # Both old and new DB conventions
        self.assertIn(DB_STATEMENT, query_span.attributes)
        self.assertIn(DB_SYSTEM, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM], "sqlite")
        self.assertIn(DB_QUERY_TEXT, query_span.attributes)
        self.assertIn(DB_SYSTEM_NAME, query_span.attributes)
        self.assertEqual(query_span.attributes[DB_SYSTEM_NAME], "sqlite")

    def test_suppress_instrumentation_cursor_and_metric(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
        )

        with suppress_instrumentation():
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 + 1;")).fetchall()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        metric_list = self.get_sorted_metrics()
        self.assertEqual(len(metric_list), 0)

    def test_get_db_name_from_cursor_postgresql_success(self):
        mock_cursor = mock.Mock()
        mock_connection = mock.Mock()
        mock_info = mock.Mock()
        mock_info.dbname = "test_database"
        mock_connection.info = mock_info
        mock_cursor.connection = mock_connection
        result = _get_db_name_from_cursor("postgresql", mock_cursor)
        self.assertEqual(result, "test_database")

    def test_get_db_name_from_cursor_postgresql_no_connection(self):
        mock_cursor = mock.Mock()
        mock_cursor.connection = None
        result = _get_db_name_from_cursor("postgresql", mock_cursor)
        self.assertIsNone(result)

    def test_get_db_name_from_cursor_postgresql_no_dbname(self):
        mock_cursor = mock.Mock()
        mock_connection = mock.Mock()
        mock_info = mock.Mock()
        mock_info.dbname = None
        mock_connection.info = mock_info
        mock_cursor.connection = mock_connection
        result = _get_db_name_from_cursor("postgresql", mock_cursor)
        self.assertIsNone(result)

    def test_get_db_name_from_cursor_unknown_vendor(self):
        mock_cursor = mock.Mock()
        mock_connection = mock.Mock()
        mock_cursor.connection = mock_connection
        result = _get_db_name_from_cursor("unknown_db", mock_cursor)
        self.assertIsNone(result)
