# Copyright 2020, OpenTelemetry Authors
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

from concurrent import futures
import threading
from opentelemetry.test.test_base import TestBase
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry import trace


class TestThreading(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        self.global_context = None
        self.global_trace_id = None
        self.global_span_id = None
        ThreadingInstrumentor().instrument()

    def tearDown(self):
        ThreadingInstrumentor().uninstrument()
        super().tearDown()

    def get_root_span(self):
        return self._tracer.start_as_current_span("rootSpan")

    def test_trace_context_propagation_in_thread(self):
        self.run_threading_test(threading.Thread(target=self.fake_func))

    def test_trace_context_propagation_in_timer(self):
        self.run_threading_test(
            threading.Timer(interval=1, function=self.fake_func)
        )

    def run_threading_test(self, thread: threading.Thread):
        with self.get_root_span() as span:
            span_context = span.get_span_context()
            expected_context = span_context
            expected_trace_id = span_context.trace_id
            expected_span_id = span_context.span_id
            thread.start()
            thread.join()

            # check result
            self.assertEqual(self.global_context, expected_context)
            self.assertEqual(self.global_trace_id, expected_trace_id)
            self.assertEqual(self.global_span_id, expected_span_id)

    def test_trace_context_propagation_in_thread_pool(self):
        with self.get_root_span() as span:
            span_context = span.get_span_context()
            expected_context = span_context
            expected_trace_id = span_context.trace_id
            expected_span_id = span_context.span_id

            with futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.fake_func)
                future.result()

                # check result
                self.assertEqual(self.global_context, expected_context)
                self.assertEqual(self.global_trace_id, expected_trace_id)
                self.assertEqual(self.global_span_id, expected_span_id)

    def fake_func(self):
        span_context = trace.get_current_span().get_span_context()
        self.global_context = span_context
        self.global_trace_id = span_context.trace_id
        self.global_span_id = span_context.span_id
