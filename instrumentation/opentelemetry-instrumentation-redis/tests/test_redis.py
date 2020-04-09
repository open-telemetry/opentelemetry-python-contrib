# -*- coding: utf-8 -*-
import unittest

import redis

from ddtrace import Pin
from opentelemetry import trace
from opentelemetry.instrumentation.redis.patch import patch, unpatch
from opentelemetry.sdk.trace import Tracer, TracerProvider
from opentelemetry.sdk.trace.export import SimpleExportSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
}


class TestRedisPatch(unittest.TestCase):

    TEST_SERVICE = "redis-patch"
    TEST_PORT = REDIS_CONFIG["port"]

    def get_spans(self):
        return self._span_exporter.get_finished_spans()

    @classmethod
    def setUpClass(cls):
        cls._tracer_provider = TracerProvider()
        trace.set_tracer_provider(cls._tracer_provider)
        cls._tracer = Tracer(cls._tracer_provider, None)
        cls._span_exporter = InMemorySpanExporter()
        cls._span_processor = SimpleExportSpanProcessor(cls._span_exporter)
        cls._tracer_provider.add_span_processor(cls._span_processor)

    def setUp(self):
        super(TestRedisPatch, self).setUp()
        patch()
        redis_client = redis.Redis(port=self.TEST_PORT)
        redis_client.flushall()
        Pin.override(
            redis_client, service=self.TEST_SERVICE, tracer=self._tracer
        )
        self.redis_client = redis_client
        self._span_exporter.clear()

    def tearDown(self):
        unpatch()
        super(TestRedisPatch, self).tearDown()

    def test_long_command(self):
        self.redis_client.mget(*range(1000))

        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        meta = {
            "out.host": "localhost",
        }
        # TODO: bring back once we add metrics
        # metrics = {
        #     "out.port": self.TEST_PORT,
        #     "out.redis_db": 0,
        # }
        for key, value in meta.items():
            assert span.attributes.get(key) == value
        # TODO: bring back once we add metrics
        # for k, v in metrics.items():
        #     assert span.get_metric(k) == v

        assert span.attributes.get("redis.raw_command").startswith(
            "MGET 0 1 2 3"
        )
        assert span.attributes.get("redis.raw_command").endswith("...")

    def test_basics(self):
        us = self.redis_client.get("cheese")
        assert us is None
        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        # TODO: bring back once we add metrics
        # assert span.get_metric("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"
        assert span.attributes.get("redis.raw_command") == "GET cheese"
        # TODO: bring back once we add metrics
        # assert span.get_metric("redis.args_length") == 2

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
        assert span.name == "redis.command"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        # assert span.get_metric("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"
        assert (
            span.attributes.get("redis.raw_command")
            == "SET blah 32\nRPUSH foo éé\nHGETALL xxx"
        )
        # assert span.get_metric("redis.pipeline_length") == 3
        # assert span.get_metric("redis.pipeline_length") == 3

    def test_pipeline_immediate(self):
        with self.redis_client.pipeline() as pipeline:
            pipeline.set("a", 1)
            pipeline.immediate_execute_command("SET", "a", 1)
            pipeline.execute()

        spans = self.get_spans()
        assert len(spans) == 2
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert span.attributes.get("redis.raw_command") == "SET a 1"
        assert (
            span.status.canonical_code == trace.status.StatusCanonicalCode.OK
        )
        # assert span.get_metric("out.redis_db") == 0
        assert span.attributes.get("out.host") == "localhost"

    def test_meta_override(self):
        redis_client = self.redis_client
        pin = Pin.get_from(redis_client)
        if pin:
            pin.clone(tags={"cheese": "camembert"}).onto(redis_client)

        redis_client.get("cheese")
        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.attributes["service"] == self.TEST_SERVICE
        # TODO: is this test needed?
        # assert "cheese" in span.attributes and span.attributes["cheese"] == "camembert"

    def test_patch_unpatch(self):
        # Test patch idempotence
        patch()
        patch()

        redis_client = redis.Redis(port=REDIS_CONFIG["port"])
        redis_client.get("key")

        spans = self.get_spans()
        self._span_exporter.clear()
        assert spans, spans
        assert len(spans) == 1

        # Test unpatch
        unpatch()

        redis_client = redis.Redis(port=REDIS_CONFIG["port"])
        redis_client.get("key")

        spans = self.get_spans()
        self._span_exporter.clear()
        assert not spans, spans

        # Test patch again
        patch()

        redis_client = redis.Redis(port=REDIS_CONFIG["port"])
        redis_client.get("key")

        spans = self.get_spans()
        self._span_exporter.clear()
        assert spans, spans
        assert len(spans) == 1

    def test_opentelemetry(self):
        """Ensure OpenTelemetry works with redis."""
        ot_tracer = trace.get_tracer("redis_svc")

        with ot_tracer.start_as_current_span("redis_get"):
            us = self.redis_client.get("cheese")
            assert us is None

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
        assert child_span.name == "redis.command"
        assert (
            child_span.status.canonical_code
            == trace.status.StatusCanonicalCode.OK
        )
        # assert dd_span.get_metric("out.redis_db") == 0
        assert child_span.attributes.get("out.host") == "localhost"
        assert child_span.attributes.get("redis.raw_command") == "GET cheese"
        # assert dd_span.get_metric("redis.args_length") == 2
