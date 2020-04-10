# -*- coding: utf-8 -*-
import unittest

import redis

from opentelemetry import trace
from opentelemetry.instrumentation.redis.patch import patch, unpatch
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleExportSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
}


class TestRedisPatch(unittest.TestCase):

    TEST_SERVICE = "redis"
    TEST_PORT = REDIS_CONFIG["port"]

    def get_spans(self):
        return self._span_exporter.get_finished_spans()

    @classmethod
    def setUpClass(cls):
        cls._tracer_provider = TracerProvider()
        trace.set_tracer_provider(cls._tracer_provider)
        cls._tracer = trace.get_tracer(cls.TEST_SERVICE)
        cls._span_exporter = InMemorySpanExporter()
        cls._span_processor = SimpleExportSpanProcessor(cls._span_exporter)
        cls._tracer_provider.add_span_processor(cls._span_processor)

    def setUp(self):
        patch()
        self.redis_client = redis.Redis(port=self.TEST_PORT)
        self.redis_client.flushall()
        self._span_exporter.clear()

    def tearDown(self):
        unpatch()

    def test_long_command(self):
        self.redis_client.mget(*range(1000))

        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name.startswith("MGET 0 1 2 3")
        assert span.name.endswith("...")
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )

        assert span.attributes.get("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"
        assert span.attributes.get("out.port") == self.TEST_PORT

        assert span.attributes.get("redis.raw_command").startswith(
            "MGET 0 1 2 3"
        )
        assert span.attributes.get("redis.raw_command").endswith("...")

    def test_basics(self):
        assert self.redis_client.get("cheese") is None
        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name == "GET cheese"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        assert span.attributes.get("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"
        assert span.attributes.get("redis.raw_command") == "GET cheese"
        assert span.attributes.get("redis.args_length") == 2

    def test_pipeline_traced(self):
        with self.redis_client.pipeline(transaction=False) as pipeline:
            pipeline.set("blah", 32)
            pipeline.rpush("foo", "éé")
            pipeline.hgetall("xxx")
            pipeline.execute()

        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name == "SET blah 32\nRPUSH foo éé\nHGETALL xxx"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        assert span.attributes.get("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"
        assert (
            span.attributes.get("redis.raw_command")
            == "SET blah 32\nRPUSH foo éé\nHGETALL xxx"
        )
        assert span.attributes.get("redis.pipeline_length") == 3

    def test_pipeline_immediate(self):
        with self.redis_client.pipeline() as pipeline:
            pipeline.set("a", 1)
            pipeline.immediate_execute_command("SET", "a", 1)
            pipeline.execute()

        spans = self.get_spans()
        assert len(spans) == 2
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name == "SET a 1"
        assert span.attributes.get("redis.raw_command") == "SET a 1"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        assert span.attributes.get("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"

    def test_meta_override(self):
        self.redis_client.get("cheese")
        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE

    def test_patch_unpatch(self):
        # Test patch idempotence
        patch()
        patch()

        self.redis_client.get("key")

        spans = self.get_spans()
        self._span_exporter.clear()
        assert spans, spans
        assert len(spans) == 1

        # Test unpatch
        unpatch()

        self.redis_client.get("key")

        spans = self.get_spans()
        self._span_exporter.clear()
        assert not spans, spans

        # Test patch again
        patch()

        self.redis_client.get("key")

        spans = self.get_spans()
        self._span_exporter.clear()
        assert spans, spans
        assert len(spans) == 1

    def test_opentelemetry(self):
        """Ensure OpenTelemetry works with redis."""
        ot_tracer = trace.get_tracer("redis_svc")

        with ot_tracer.start_as_current_span("redis_get"):
            assert self.redis_client.get("cheese") is None

        spans = self.get_spans()
        assert len(spans) == 2
        child_span, parent_span = spans[0], spans[1]

        # confirm the parenting
        assert parent_span.parent is None
        assert (
            child_span.parent.context.trace_id == parent_span.context.trace_id
        )

        assert parent_span.name == "redis_get"
        assert parent_span.instrumentation_info.name == "redis_svc"

        assert child_span.attributes.get("service") == self.TEST_SERVICE
        assert child_span.name == "GET cheese"
        assert (
            child_span.status.canonical_code
            == trace.status.StatusCanonicalCode.OK
        )
        assert child_span.attributes.get("out.redis_db") == 0
        assert child_span.attributes.get("out.host") == "localhost"
        assert child_span.attributes.get("redis.raw_command") == "GET cheese"
        assert child_span.attributes.get("redis.args_length") == 2
