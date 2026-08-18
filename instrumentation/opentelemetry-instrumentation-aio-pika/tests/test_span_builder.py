# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase

from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder
from opentelemetry.trace import Span, get_tracer


class TestBuilder(TestCase):
    def test_build(self):
        builder = SpanBuilder(get_tracer(__name__))
        builder.set_as_consumer()
        builder.set_destination("destination")
        span = builder.build()
        self.assertTrue(isinstance(span, Span))
