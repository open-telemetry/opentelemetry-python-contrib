# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import threading
import time
from platform import python_implementation
from timeit import default_timer

from pytest import mark

from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.test.test_base import TestBase

from .celery_test_tasks import app, task_add

SCOPE = "opentelemetry.instrumentation.celery"


def wait_for(predicate, message, timeout_s=60):
    """Poll ``predicate`` until it is true, failing the test if it never is."""
    deadline = time.time() + timeout_s
    while not predicate():
        if time.time() > deadline:
            raise AssertionError(f"timed out after {timeout_s}s waiting for {message}")
        time.sleep(0.05)


def run_task():
    """Run a task and wait for it to finish."""
    result = task_add.delay(1, 2)
    wait_for(result.ready, "the task to finish")


class TestMetrics(TestBase):
    def setUp(self):
        super().setUp()
        self._worker = app.Worker(app=app, pool="solo", concurrency=1, hostname="celery@akochavi")
        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        super().tearDown()
        self._worker.stop()
        self._thread.join()

    def recorded_run_count(self):
        metrics = self.get_sorted_metrics(SCOPE)
        if not metrics:
            return 0
        return sum(point.count for point in metrics[0].data.data_points)

    def get_metrics(self, expected_run_count=1):
        """Run a task and return the metrics once its runtime is recorded.

        Celery stores the task result before it dispatches ``task_postrun``, and
        the instrumentation records the runtime histogram from its
        ``task_postrun`` receiver. So an ``AsyncResult`` can be ready while the
        histogram has not been recorded yet, and waiting on ``result.ready()``
        alone makes the metric assertions racy.
        """
        task_add.delay(1, 2)
        wait_for(
            lambda: self.recorded_run_count() >= expected_run_count,
            f"{expected_run_count} task runs to be recorded",
        )
        return self.get_sorted_metrics(SCOPE)

    def test_basic_metric(self):
        CeleryInstrumentor().instrument()
        start_time = default_timer()
        task_runtime_estimated = (default_timer() - start_time) * 1000

        metrics = self.get_metrics()
        CeleryInstrumentor().uninstrument()
        self.assertEqual(len(metrics), 1)

        task_runtime = metrics[0]
        print(task_runtime)
        self.assertEqual(task_runtime.name, "flower.task.runtime.seconds")
        self.assert_metric_expected(
            task_runtime,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=task_runtime_estimated,
                    max_data_point=task_runtime_estimated,
                    min_data_point=task_runtime_estimated,
                    attributes={
                        "task": "tests.celery_test_tasks.task_add",
                        "worker": "celery@akochavi",
                    },
                )
            ],
            est_value_delta=200,
        )

    @mark.skipif(python_implementation() == "PyPy", reason="Fails randomly in pypy")
    def test_metric_uninstrument(self):
        CeleryInstrumentor().instrument()

        metrics = self.get_metrics(1)
        self.assertEqual(
            metrics[0].data.data_points[0].bucket_counts[1],
            1,
        )

        metrics = self.get_metrics(2)
        self.assertEqual(
            metrics[0].data.data_points[0].bucket_counts[1],
            2,
        )

        CeleryInstrumentor().uninstrument()

        # nothing is recorded once uninstrumented, so there is no metric to wait
        # for here; the task finishing is what makes the assertion meaningful
        run_task()
        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(
            metrics[0].data.data_points[0].bucket_counts[1],
            2,
        )
