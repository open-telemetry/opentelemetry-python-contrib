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

import threading
from concurrent import futures

from opentelemetry import trace
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.test.test_base import TestBase


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

    def print_square(self, num):
        with self._tracer.start_as_current_span("square"):
            return num * num

    def print_cube(self, num):
        with self._tracer.start_as_current_span("cube"):
            return num * num * num

    def print_square_with_thread(self, num):
        with self._tracer.start_as_current_span("square"):
            cube_thread = threading.Thread(target=self.print_cube, args=(10,))

            cube_thread.start()
            cube_thread.join()
            return num * num

    def calculate(self, num):
        with self._tracer.start_as_current_span("calculate"):
            square_thread = threading.Thread(
                target=self.print_square, args=(num,)
            )
            cube_thread = threading.Thread(target=self.print_cube, args=(num,))
            square_thread.start()
            square_thread.join()

            cube_thread.start()
            cube_thread.join()

    def test_without_thread_nesting(self):
        square_thread = threading.Thread(target=self.print_square, args=(10,))

        with self._tracer.start_as_current_span("root"):
            square_thread.start()
            square_thread.join()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        # pylint: disable=unbalanced-tuple-unpacking
        target, root = spans[:2]

        self.assertIs(target.parent, root.get_span_context())
        self.assertIsNone(root.parent)

    def test_with_thread_nesting(self):
        #
        #  Following scenario is tested.
        #  threadA -> methodA -> threadB -> methodB
        #

        square_thread = threading.Thread(
            target=self.print_square_with_thread, args=(10,)
        )

        with self._tracer.start_as_current_span("root"):
            square_thread.start()
            square_thread.join()

        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 3)
        # pylint: disable=unbalanced-tuple-unpacking
        cube, square, root = spans[:3]

        self.assertIs(cube.parent, square.get_span_context())
        self.assertIs(square.parent, root.get_span_context())
        self.assertIsNone(root.parent)

    def test_with_thread_multi_nesting(self):
        #
        # Following scenario is tested.
        #                         / threadB -> methodB
        #    threadA -> methodA ->
        #                        \ threadC -> methodC
        #
        calculate_thread = threading.Thread(target=self.calculate, args=(10,))

        with self._tracer.start_as_current_span("root"):
            calculate_thread.start()
            calculate_thread.join()

        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 4)

        # pylint: disable=unbalanced-tuple-unpacking
        cube, square, calculate, root = spans[:4]

        self.assertIs(cube.parent, calculate.get_span_context())
        self.assertIs(square.parent, calculate.get_span_context())
        self.assertIs(calculate.parent, root.get_span_context())
        self.assertIsNone(root.parent)

    def test_uninstrumented(self):
        ThreadingInstrumentor().uninstrument()

        square_thread = threading.Thread(target=self.print_square, args=(10,))
        square_thread.start()
        square_thread.join()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        ThreadingInstrumentor().instrument()
