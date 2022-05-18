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
from unittest import TestCase

from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder
from opentelemetry.trace import Span


class TestBuilder(TestCase):
    def test_build(self):
        builder = SpanBuilder()
        builder.set_as_consumer()
        builder.set_destination('destination')
        span = builder.build()
        self.assertTrue(isinstance(span, Span))
    
    def test_no_destination(self):
        builder = SpanBuilder()
        builder.set_as_consumer()
        with self.assertRaises(AssertionError):
            builder.build()
    
    def test_no_kind(self):
        builder = SpanBuilder()
        builder.set_destination('destination')
        with self.assertRaises(AssertionError):
            builder.build()
