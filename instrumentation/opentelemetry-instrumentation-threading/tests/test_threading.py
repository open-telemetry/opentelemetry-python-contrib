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
from concurrent.futures import ThreadPoolExecutor
from typing import List

from opentelemetry import trace
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.test.test_base import TestBase


class TestThreading(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        self._mock_span_contexts: List[trace.SpanContext] = []
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
            expected_span_context = span.get_span_context()
            thread.start()
            thread.join()

            # check result
            self.assertEqual(len(self._mock_span_contexts), 1)
            self.assertEqual(
                self._mock_span_contexts[0], expected_span_context
            )

    def test_trace_context_propagation_in_thread_pool_with_multiple_workers(
        self,
    ):
        max_workers = 10
        executor = ThreadPoolExecutor(max_workers=max_workers)

        expected_span_contexts: List[trace.SpanContext] = []
        futures_list = []
        for num in range(max_workers):
            with self._tracer.start_as_current_span(f"trace_{num}") as span:
                expected_span_context = span.get_span_context()
                expected_span_contexts.append(expected_span_context)
                future = executor.submit(
                    self.get_current_span_context_for_test
                )
                futures_list.append(future)

        result_span_contexts = [future.result() for future in futures_list]

        # check result
        self.assertEqual(result_span_contexts, expected_span_contexts)

    def test_trace_context_propagation_in_thread_pool_with_single_worker(self):
        max_workers = 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # test propagation of the same trace context across multiple tasks
            with self._tracer.start_as_current_span("task") as task_span:
                expected_task_context = task_span.get_span_context()
                future1 = executor.submit(
                    self.get_current_span_context_for_test
                )
                future2 = executor.submit(
                    self.get_current_span_context_for_test
                )

                # check result
                self.assertEqual(future1.result(), expected_task_context)
                self.assertEqual(future2.result(), expected_task_context)

            # test propagation of different trace contexts across tasks in sequence
            with self._tracer.start_as_current_span("task1") as task1_span:
                expected_task1_context = task1_span.get_span_context()
                future1 = executor.submit(
                    self.get_current_span_context_for_test
                )

                # check result
                self.assertEqual(future1.result(), expected_task1_context)

            with self._tracer.start_as_current_span("task2") as task2_span:
                expected_task2_context = task2_span.get_span_context()
                future2 = executor.submit(
                    self.get_current_span_context_for_test
                )

                # check result
                self.assertEqual(future2.result(), expected_task2_context)

    def fake_func(self):
        span_context = self.get_current_span_context_for_test()
        self._mock_span_contexts.append(span_context)

    @staticmethod
    def get_current_span_context_for_test() -> trace.SpanContext:
        return trace.get_current_span().get_span_context()

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
