from unittest import TestCase

from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder
from opentelemetry.trace import Span, get_tracer

# https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/#messaging-attributes
# use as example: opentelemetry-instrumentation-redis/tests/test_redis.py


REQUIRED_SPAN_ATTRIBUTES = {
    "messaging.operation.type": {
        "type": str()
    },
    "messaging.system": {
        "type": str()
    },
}
CONDITIONALLY_REQUIRED_SPAN_ATTRIBUTES = {
    "error.type" : {
        "type": str()
    },
    "messaging.batch.message_count" : {
        "type": int()
    },
    "messaging.destination.anonymous" : {
        "type": bool()
    },
    "messaging.destination.name" : {
        "type": str()
    },
    "messaging.destination.template" : {
        "type": str()
    },
    "messaging.destination.temporary" : {
        "type": bool()
    },
    "server.address" : {
        "type": str()
    },
}


class TestBuilder(TestCase):
    def test_consumer_required_attributes(self):
        builder = SpanBuilder(get_tracer(__name__))
        builder.set_as_consumer()
        builder.set_destination("destination")
        span = builder.build()
        self.assertTrue(isinstance(span, Span))

    def test_producer_required_attributes(self):
        builder = SpanBuilder(get_tracer(__name__))
        builder.set_as_producer()
        builder.set_destination("destination")
        span = builder.build()
        self.assertTrue(isinstance(span, Span))
