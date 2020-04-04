# -*- coding: utf-8 -*-
import redis

from ddtrace import Pin, compat
from ddtrace.constants import ANALYTICS_SAMPLE_RATE_KEY
from ddtrace.contrib.redis.patch import patch, unpatch

from tests.opentracer.utils import init_tracer
from ..config import REDIS_CONFIG
from ...test_tracer import get_dummy_tracer
from ...base import BaseTracerTestCase


class TestRedisPatch(BaseTracerTestCase):

    TEST_SERVICE = "redis-patch"
    TEST_PORT = REDIS_CONFIG["port"]

    def setUp(self):
        super(TestRedisPatch, self).setUp()
        patch()
        r = redis.Redis(port=self.TEST_PORT)
        r.flushall()
        Pin.override(r, service=self.TEST_SERVICE, tracer=self.tracer)
        self.r = r

    def tearDown(self):
        unpatch()
        super(TestRedisPatch, self).tearDown()

    def test_long_command(self):
        self.r.mget(*range(1000))

        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.service == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert span.span_type == "redis"
        assert span.error == 0
        meta = {
            "out.host": "localhost",
        }
        metrics = {
            "out.port": self.TEST_PORT,
            "out.redis_db": 0,
        }
        for k, v in meta.items():
            assert span.get_tag(k) == v
        for k, v in metrics.items():
            assert span.get_metric(k) == v

        assert span.get_tag("redis.raw_command").startswith("MGET 0 1 2 3")
        assert span.get_tag("redis.raw_command").endswith("...")

    def test_basics(self):
        us = self.r.get("cheese")
        assert us is None
        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.service == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert span.span_type == "redis"
        assert span.error == 0
        assert span.get_metric("out.redis_db") == 0
        assert span.get_tag("out.host") == "localhost"
        assert span.get_tag("redis.raw_command") == "GET cheese"
        assert span.get_metric("redis.args_length") == 2
        assert span.resource == "GET cheese"
        assert span.get_metric(ANALYTICS_SAMPLE_RATE_KEY) is None

    def test_analytics_without_rate(self):
        with self.override_config("redis", dict(analytics_enabled=True)):
            us = self.r.get("cheese")
            assert us is None
            spans = self.get_spans()
            assert len(spans) == 1
            span = spans[0]
            assert span.get_metric(ANALYTICS_SAMPLE_RATE_KEY) == 1.0

    def test_analytics_with_rate(self):
        with self.override_config("redis", dict(analytics_enabled=True, analytics_sample_rate=0.5)):
            us = self.r.get("cheese")
            assert us is None
            spans = self.get_spans()
            assert len(spans) == 1
            span = spans[0]
            assert span.get_metric(ANALYTICS_SAMPLE_RATE_KEY) == 0.5

    def test_pipeline_traced(self):
        with self.r.pipeline(transaction=False) as p:
            p.set("blah", 32)
            p.rpush("foo", "éé")
            p.hgetall("xxx")
            p.execute()

        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.service == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert span.resource == "SET blah 32\nRPUSH foo éé\nHGETALL xxx"
        assert span.span_type == "redis"
        assert span.error == 0
        assert span.get_metric("out.redis_db") == 0
        assert span.get_tag("out.host") == "localhost"
        assert span.get_tag("redis.raw_command") == "SET blah 32\nRPUSH foo éé\nHGETALL xxx"
        assert span.get_metric("redis.pipeline_length") == 3
        assert span.get_metric("redis.pipeline_length") == 3
        assert span.get_metric(ANALYTICS_SAMPLE_RATE_KEY) is None

    def test_pipeline_immediate(self):
        with self.r.pipeline() as p:
            p.set("a", 1)
            p.immediate_execute_command("SET", "a", 1)
            p.execute()

        spans = self.get_spans()
        assert len(spans) == 2
        span = spans[0]
        assert span.service == self.TEST_SERVICE
        assert span.name == "redis.command"
        assert span.resource == "SET a 1"
        assert span.span_type == "redis"
        assert span.error == 0
        assert span.get_metric("out.redis_db") == 0
        assert span.get_tag("out.host") == "localhost"

    def test_meta_override(self):
        r = self.r
        pin = Pin.get_from(r)
        if pin:
            pin.clone(tags={"cheese": "camembert"}).onto(r)

        r.get("cheese")
        spans = self.get_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.service == self.TEST_SERVICE
        assert "cheese" in span.meta and span.meta["cheese"] == "camembert"

    def test_patch_unpatch(self):
        tracer = get_dummy_tracer()
        writer = tracer.writer

        # Test patch idempotence
        patch()
        patch()

        r = redis.Redis(port=REDIS_CONFIG["port"])
        Pin.get_from(r).clone(tracer=tracer).onto(r)
        r.get("key")

        spans = writer.pop()
        assert spans, spans
        assert len(spans) == 1

        # Test unpatch
        unpatch()

        r = redis.Redis(port=REDIS_CONFIG["port"])
        r.get("key")

        spans = writer.pop()
        assert not spans, spans

        # Test patch again
        patch()

        r = redis.Redis(port=REDIS_CONFIG["port"])
        Pin.get_from(r).clone(tracer=tracer).onto(r)
        r.get("key")

        spans = writer.pop()
        assert spans, spans
        assert len(spans) == 1

    def test_opentracing(self):
        """Ensure OpenTracing works with redis."""
        ot_tracer = init_tracer("redis_svc", self.tracer)

        with ot_tracer.start_active_span("redis_get"):
            us = self.r.get("cheese")
            assert us is None

        spans = self.get_spans()
        assert len(spans) == 2
        ot_span, dd_span = spans

        # confirm the parenting
        assert ot_span.parent_id is None
        assert dd_span.parent_id == ot_span.span_id

        assert ot_span.name == "redis_get"
        assert ot_span.service == "redis_svc"

        assert dd_span.service == self.TEST_SERVICE
        assert dd_span.name == "redis.command"
        assert dd_span.span_type == "redis"
        assert dd_span.error == 0
        assert dd_span.get_metric("out.redis_db") == 0
        assert dd_span.get_tag("out.host") == "localhost"
        assert dd_span.get_tag("redis.raw_command") == "GET cheese"
        assert dd_span.get_metric("redis.args_length") == 2
        assert dd_span.resource == "GET cheese"

