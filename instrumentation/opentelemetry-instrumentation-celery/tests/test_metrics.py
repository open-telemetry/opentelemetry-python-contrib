import time
import threading
from timeit import default_timer
from typing import Union, Optional

from opentelemetry.sdk.metrics._internal.point import Metric
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from .celery_test_tasks import task_add, app


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
        resource_metrics = (
            self.memory_metrics_reader.get_metrics_data().resource_metrics
        )

        all_metrics = []
        for metrics in resource_metrics:
            for scope_metrics in metrics.scope_metrics:
                all_metrics.extend(scope_metrics.metrics)

        return all_metrics

    def assert_metric_expected(
        self,
        metric: Metric,
        expected_value: Union[int, float],
        expected_attributes: dict = None,
        est_delta: Optional[float] = None,
    ):
        data_point = next(iter(metric.data.data_points))

        if isinstance(data_point, HistogramDataPoint):
            self.assertEqual(
                data_point.count,
                1,
            )
            if est_delta is None:
                self.assertEqual(
                    data_point.sum,
                    expected_value,
                )
            else:
                self.assertAlmostEqual(
                    data_point.sum,
                    expected_value,
                    delta=est_delta,
                )
        elif isinstance(data_point, NumberDataPoint):
            self.assertEqual(
                data_point.value,
                expected_value,
            )

        if expected_attributes:
            self.assertDictEqual(
                expected_attributes,
                dict(data_point.attributes),
            )

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
            task_runtime_estimated,
            {
                "task": "tests.celery_test_tasks.task_add",
                "worker": "celery@akochavi",
            },
            est_delta=200,
        )

    def test_metric_uninstrument(self):
        CeleryInstrumentor().instrument()
        metrics = self.get_metrics()
        self.assertEqual(len(metrics), 1)
        CeleryInstrumentor().uninstrument()

        metrics = self.get_metrics()
        self.assertEqual(len(metrics), 1)

        for metric in metrics:
            for point in list(metric.data.data_points):
                self.assertEqual(point.count, 1)
