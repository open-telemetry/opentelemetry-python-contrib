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
import logging
import re

import pytest
from sqlalchemy import (
    create_engine,
    text,
)

from opentelemetry import context
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase


class TestSqlalchemyInstrumentationWithSQLCommenter(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog

    def tearDown(self):
        super().tearDown()
        SQLAlchemyInstrumentor().uninstrument()

    def test_sqlcommenter_disabled(self):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        engine = create_engine("sqlite:///:memory:", echo=True)
        SQLAlchemyInstrumentor().instrument(
            engine=engine, tracer_provider=self.tracer_provider
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT 1;")).fetchall()

        self.assertEqual(self.caplog.records[-2].getMessage(), "SELECT 1;")

    def test_sqlcommenter_enabled(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={"db_framework": False},
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_sqlcommenter_default_stmt_enabled_no_comments_anywhere(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            # enable_commenter not set
            enable_attribute_commenter=True,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        query_log = self.caplog.records[-2].getMessage()
        self.assertEqual(
            query_log,
            "SELECT  1;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            "SELECT  1;",
        )

    def test_sqlcommenter_disabled_stmt_enabled_no_comments_anywhere(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=False,
            enable_attribute_commenter=True,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        query_log = self.caplog.records[-2].getMessage()
        self.assertEqual(
            query_log,
            "SELECT  1;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            "SELECT  1;",
        )

    def test_sqlcommenter_enabled_stmt_disabled_default(
        self,
    ):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={"db_framework": False},
            # enable_attribute_commenter not set
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        query_log = self.caplog.records[-2].getMessage()
        self.assertRegex(
            query_log,
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            "SELECT  1;",
        )

    def test_sqlcommenter_enabled_stmt_enabled_matches_db_statement_attribute(
        self,
    ):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={"db_framework": False},
            enable_attribute_commenter=True,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
        query_log = self.caplog.records[-2].getMessage()
        self.assertRegex(
            query_log,
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertRegex(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            r"SELECT  1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        cnx_span_id = re.search(r"[a-zA-Z0-9_]{16}", query_log).group()
        db_statement_span_id = re.search(
            r"[a-zA-Z0-9_]{16}",
            query_span.attributes[SpanAttributes.DB_STATEMENT],
        ).group()
        self.assertEqual(cnx_span_id, db_statement_span_id)

    def test_sqlcommenter_enabled_otel_values_false(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={
                "db_framework": False,
                "opentelemetry_values": False,
            },
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
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
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            r"SELECT  1;",
        )

    def test_sqlcommenter_enabled_stmt_enabled_otel_values_false(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={
                "db_framework": False,
                "opentelemetry_values": False,
            },
            enable_attribute_commenter=True,
        )
        cnx = engine.connect()
        cnx.execute(text("SELECT  1;")).fetchall()
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
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            r"SELECT  1 /\*db_driver='(.*)'*/;",
        )

    def test_sqlcommenter_flask_integration(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={"db_framework": False},
        )
        cnx = engine.connect()

        current_context = context.get_current()
        sqlcommenter_context = context.set_value(
            "SQLCOMMENTER_ORM_TAGS_AND_VALUES", {"flask": 1}, current_context
        )
        context.attach(sqlcommenter_context)

        cnx.execute(text("SELECT  1;")).fetchall()
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)',flask=1,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            "SELECT  1;",
        )

    def test_sqlcommenter_stmt_enabled_flask_integration(self):
        engine = create_engine("sqlite:///:memory:")
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            commenter_options={"db_framework": False},
            enable_attribute_commenter=True,
        )
        cnx = engine.connect()

        current_context = context.get_current()
        sqlcommenter_context = context.set_value(
            "SQLCOMMENTER_ORM_TAGS_AND_VALUES", {"flask": 1}, current_context
        )
        context.attach(sqlcommenter_context)

        cnx.execute(text("SELECT  1;")).fetchall()
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT  1 /\*db_driver='(.*)',flask=1,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertRegex(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            r"SELECT  1 /\*db_driver='(.*)',flask=1,traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_sqlcommenter_enabled_create_engine_after_instrumentation(self):
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT 1;")).fetchall()
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT 1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertEqual(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            "SELECT 1;",
        )

    def test_sqlcommenter_enabled_stmt_enabled_create_engine_after_instrumentation(
        self,
    ):
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            enable_commenter=True,
            enable_attribute_commenter=True,
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT 1;")).fetchall()
        self.assertRegex(
            self.caplog.records[-2].getMessage(),
            r"SELECT 1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        # first span is connection to db
        self.assertEqual(spans[0].name, "connect")
        # second span is query itself
        query_span = spans[1]
        self.assertRegex(
            query_span.attributes[SpanAttributes.DB_STATEMENT],
            r"SELECT 1 /\*db_driver='(.*)',traceparent='\d{1,2}-[a-zA-Z0-9_]{32}-[a-zA-Z0-9_]{16}-\d{1,2}'\*/;",
        )

    def test_sqlcommenter_disabled_create_engine_after_instrumentation(self):
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            enable_commenter=False,
        )
        from sqlalchemy import (  # noqa: PLC0415
            create_engine,  # pylint: disable-all
        )

        engine = create_engine("sqlite:///:memory:")
        cnx = engine.connect()
        cnx.execute(text("SELECT 1;")).fetchall()
        self.assertEqual(self.caplog.records[-2].getMessage(), "SELECT 1;")
