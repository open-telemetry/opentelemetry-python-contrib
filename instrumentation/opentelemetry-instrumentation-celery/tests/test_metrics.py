import threading
import time
from platform import python_implementation
from timeit import default_timer

from pytest import mark

from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.test.test_base import TestBase

from .celery_test_tasks import app, task_add


class TestMetrics(TestBase):
    def setUp(self):
        super().setUp()
        self._worker = app.Worker(
            app=app, pool="solo", concurrency=1, hostname="celery@akochavi"
        )
        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        super().tearDown()
        self._worker.stop()
        self._thread.join()

    def get_metrics(self):
        result = task_add.delay(1, 2)

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)
        return self.get_sorted_metrics()

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

    @mark.skipif(
        python_implementation() == "PyPy", reason="Fails randomly in pypy"
    )
    def test_metric_uninstrument(self):
        CeleryInstrumentor().instrument()

        self.get_metrics()
        self.assertEqual(
            (
                self.memory_metrics_reader.get_metrics_data()
                .resource_metrics[0]
                .scope_metrics[0]
                .metrics[0]
                .data.data_points[0]
                .bucket_counts[1]
            ),
            1,
        )

        self.get_metrics()
        self.assertEqual(
            (
                self.memory_metrics_reader.get_metrics_data()
                .resource_metrics[0]
                .scope_metrics[0]
                .metrics[0]
                .data.data_points[0]
                .bucket_counts[1]
            ),
            2,
        )

        CeleryInstrumentor().uninstrument()

        self.get_metrics()
        self.assertEqual(
            (
                self.memory_metrics_reader.get_metrics_data()
                .resource_metrics[0]
                .scope_metrics[0]
                .metrics[0]
                .data.data_points[0]
                .bucket_counts[1]
            ),
            2,
        )
