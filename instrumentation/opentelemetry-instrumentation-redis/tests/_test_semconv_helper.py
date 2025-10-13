import os
from unittest.mock import patch

import fakeredis
from redis.exceptions import ResponseError, WatchError

from opentelemetry import trace
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.test.test_base import TestBase


class TestRedisSemConv(TestBase):
    def setUp(self):
        super().setUp()
        self.conn_patcher = patch(
            "opentelemetry.instrumentation.redis._get_redis_conn_info",
            return_value=("localhost", 6379, 0, None),
        )
        self.conn_patcher.start()
        RedisInstrumentor().instrument(tracer_provider=self.tracer_provider)
        self.redis_client = fakeredis.FakeStrictRedis()
        self.env_mode = os.getenv("OTEL_SEMCONV_STABILITY_OPT_IN")

    def tearDown(self):
        super().tearDown()
        self.conn_patcher.stop()
        RedisInstrumentor().uninstrument()

    def test_single_command(self):
        """Tests attributes for a regular single command."""
        self.redis_client.set("key", "value")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        if self.env_mode == "database":
            self.assertEqual(span.attributes.get("db.system.name"), "redis")
            self.assertEqual(span.attributes.get("db.operation.name"), "SET")
            self.assertEqual(span.attributes.get("db.namespace"), "0")
            self.assertEqual(span.attributes.get("db.query.text"), "SET ? ?")
            self.assertNotIn(DB_SYSTEM, span.attributes)
            self.assertNotIn(DB_STATEMENT, span.attributes)
        elif self.env_mode == "database/dup":
            self.assertEqual(span.attributes.get("db.system.name"), "redis")
            self.assertEqual(span.attributes.get(DB_SYSTEM), "redis")
            self.assertEqual(span.attributes.get(DB_STATEMENT), "SET ? ?")
        else:  # Default (old) behavior
            self.assertEqual(span.attributes.get(DB_SYSTEM), "redis")
            self.assertEqual(span.attributes.get(DB_STATEMENT), "SET ? ?")
            self.assertNotIn("db.system.name", span.attributes)

    def test_pipeline_command(self):
        """Tests attributes for a pipeline command."""
        with self.redis_client.pipeline(transaction=False) as pipe:
            pipe.set("a", 1)
            pipe.get("a")
            pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        if self.env_mode in ("database", "database/dup"):
            self.assertEqual(
                span.attributes.get("db.operation.name"), "PIPELINE"
            )
            self.assertEqual(span.attributes.get("db.operation.batch.size"), 2)

    def test_stored_procedure_command(self):
        """Tests attributes for a stored procedure command."""
        with patch.object(
            self.redis_client, "parse_response", return_value=b"ok"
        ):
            self.redis_client.evalsha("some-sha", 0, "key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        if self.env_mode in ("database", "database/dup"):
            self.assertEqual(
                span.attributes.get("db.stored_procedure.name"), "some-sha"
            )
        else:
            self.assertNotIn("db.stored_procedure.name", span.attributes)

    def test_generic_error(self):
        """Tests attributes for a generic error."""
        with patch.object(
            self.redis_client,
            "parse_response",
            side_effect=ResponseError("ERR unknown command"),
        ):
            with self.assertRaises(ResponseError):
                self.redis_client.execute_command("INVALID_COMMAND")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)

        if self.env_mode in ("database", "database/dup"):
            self.assertEqual("ERR", span.attributes.get("error.type"))
            self.assertEqual(
                "ERR", span.attributes.get("db.response.status_code")
            )
        else:
            self.assertNotIn("error.type", span.attributes)
            self.assertNotIn("db.response.status_code", span.attributes)

    def test_watch_error(self):
        """Tests attributes for a WatchError."""
        with self.assertRaises(WatchError):
            with self.redis_client.pipeline(transaction=True) as pipe:
                pipe.watch("watched_key")
                self.redis_client.set("watched_key", "modified-externally")
                pipe.multi()
                pipe.set("watched_key", "new-value")
                pipe.get("watched_key")
                with patch.object(pipe, "execute", side_effect=WatchError):
                    pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        failed_pipeline_span = spans[-1]
        self.assertEqual(
            failed_pipeline_span.status.status_code, trace.StatusCode.UNSET
        )
