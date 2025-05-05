import logging
import threading
import time

import pytest
from celery.signals import task_postrun, task_prerun, task_received

from opentelemetry.instrumentation.celery import (
    _TASK_COUNT_ACTIVE,
    _TASK_COUNT_PREFETCHED,
    _TASK_PREFETCH_TIME,
    _TASK_PROCESSING_TIME,
    CeleryInstrumentor,
    TaskDurationTracker,
    _create_celery_worker_metrics,
)
from opentelemetry.metrics import get_meter
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_CLIENT_ID,
    MESSAGING_OPERATION_NAME,
)
from opentelemetry.test.test_base import TestBase

from .celery_test_tasks import (
    app,
    task_add,
    task_raises,
    task_sleep,
)

EXPECTED_METRICS = 4


class TestCeleryMetrics(TestBase):
    WORKER_NODE = "celery@hostname"

    def setUp(self):
        super().setUp()
        self._worker = app.Worker(
            app=app,
            pool="threads",
            concurrency=1,
            hostname=self.WORKER_NODE,
            loglevel="INFO",
            without_mingle=True,
            without_heartbeat=True,
            without_gossip=True,
        )

        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        super().tearDown()
        self._worker.stop()
        self._thread.join()

    def wait_for_tasks_to_finish(self):
        """Blocks until all tasks in Celery worker are finished"""

        inspect = app.control.inspect()
        while True:
            counter = 0
            for state in (
                inspect.scheduled(),
                inspect.active(),
                inspect.reserved(),
            ):
                if state is not None:
                    counter += len(state[self.WORKER_NODE])

            if counter == 0:
                break

            time.sleep(0.5)

    def wait_for_metrics_until_finished(self, task_fn, *args):
        """
        Create a task, wait for it to finish and return metrics

        This ensures that all metrics have been initialized.
        """

        result = task_fn.delay(*args)

        timeout = time.time() + 60 * 1
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)
        return self.get_sorted_metrics()

    def test_counters_are_correct(self):
        """
        Test that prefetch and execution task counters are counting correctly
        """

        CeleryInstrumentor().instrument()

        task_add.delay()
        self.wait_for_tasks_to_finish()

        task_sleep.delay(2)
        task_sleep.delay(2)
        task_sleep.delay(2)

        time.sleep(1)

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(len(exported_metrics), EXPECTED_METRICS)

        # Worker is single-threaded, so we expect 1 task_sleep to be running and
        # 2 task_sleep to be waiting in queue
        for metric in exported_metrics:
            data_point = metric.data.data_points[0]

            if not data_point.attributes.get(
                MESSAGING_OPERATION_NAME
            ).endswith("task_sleep"):
                continue

            if metric.name == _TASK_COUNT_ACTIVE:
                self.assertEqual(data_point.value, 1)

            if metric.name == _TASK_COUNT_PREFETCHED:
                self.assertEqual(data_point.value, 2)

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

    def test_counters_with_task_errors(self):
        """
        Test that counters are working well even if task is raising errors
        """

        CeleryInstrumentor().instrument()

        task_raises.delay()
        self.wait_for_tasks_to_finish()

        task_sleep.delay(2)
        task_sleep.delay(2)

        time.sleep(1)

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(len(exported_metrics), EXPECTED_METRICS)

        for metric in exported_metrics:
            data_point = metric.data.data_points[0]

            if not data_point.attributes.get(
                MESSAGING_OPERATION_NAME
            ).endswith("task_sleep"):
                continue

            if metric.name == _TASK_COUNT_ACTIVE:
                self.assertEqual(data_point.value, 1)

            if metric.name == _TASK_COUNT_PREFETCHED:
                self.assertEqual(data_point.value, 1)

        # After processing is finished, all counters should be at 0
        self.wait_for_tasks_to_finish()
        exported_metrics = self.get_sorted_metrics()

        for metric in exported_metrics:
            data_point = metric.data.data_points[0]

            if not data_point.attributes.get(
                MESSAGING_OPERATION_NAME
            ).endswith("task_sleep"):
                continue

            if metric.name == _TASK_COUNT_ACTIVE:
                self.assertEqual(data_point.value, 0)

            if metric.name == _TASK_COUNT_PREFETCHED:
                self.assertEqual(data_point.value, 0)

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

    def test_counters_with_revoked_task(self):
        CeleryInstrumentor().instrument()

        self.wait_for_metrics_until_finished(task_add)

        task_sleep.delay(2)
        task2 = task_sleep.delay(2)
        task2.revoke()

        self.wait_for_tasks_to_finish()

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(len(exported_metrics), EXPECTED_METRICS)

        for metric in exported_metrics:
            data_point = metric.data.data_points[0]

            if not data_point.attributes.get(
                MESSAGING_OPERATION_NAME
            ).endswith("task_sleep"):
                continue

            if metric.name == _TASK_COUNT_ACTIVE:
                self.assertEqual(data_point.value, 0)

            if metric.name == _TASK_COUNT_PREFETCHED:
                self.assertEqual(data_point.value, 0)

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

    def test_prefetch_duration_metric(self):
        CeleryInstrumentor().instrument()

        expected_prefetch_seconds = 1

        self.wait_for_metrics_until_finished(task_add)
        task_sleep.delay(1)
        task_sleep.delay(1)

        self.wait_for_tasks_to_finish()

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(len(exported_metrics), EXPECTED_METRICS)

        task_runtime = [
            x for x in exported_metrics if x.name == _TASK_PREFETCH_TIME
        ][0]
        self.assertEqual(task_runtime.name, _TASK_PREFETCH_TIME)
        self.assert_metric_expected(
            task_runtime,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes={
                        MESSAGING_OPERATION_NAME: "tests.celery_test_tasks.task_add",
                        MESSAGING_CLIENT_ID: self.WORKER_NODE,
                    },
                ),
                self.create_histogram_data_point(
                    count=2,
                    sum_data_point=expected_prefetch_seconds,
                    max_data_point=expected_prefetch_seconds,
                    min_data_point=0,  # First sleep task did not have to wait
                    attributes={
                        MESSAGING_OPERATION_NAME: "tests.celery_test_tasks.task_sleep",
                        MESSAGING_CLIENT_ID: self.WORKER_NODE,
                    },
                ),
            ],
            est_value_delta=0.05,
        )

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

    def test_execution_duration_metric(self):
        CeleryInstrumentor().instrument()

        expected_runtime_seconds = 2

        self.wait_for_metrics_until_finished(task_add)
        task_sleep.delay(2)

        self.wait_for_tasks_to_finish()

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(len(exported_metrics), EXPECTED_METRICS)

        task_runtime = [
            x for x in exported_metrics if x.name == _TASK_PROCESSING_TIME
        ][0]
        self.assert_metric_expected(
            task_runtime,
            [
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=0,
                    max_data_point=0,
                    min_data_point=0,
                    attributes={
                        MESSAGING_OPERATION_NAME: "tests.celery_test_tasks.task_add",
                        MESSAGING_CLIENT_ID: self.WORKER_NODE,
                    },
                ),
                self.create_histogram_data_point(
                    count=1,
                    sum_data_point=expected_runtime_seconds,
                    max_data_point=expected_runtime_seconds,
                    min_data_point=expected_runtime_seconds,
                    attributes={
                        MESSAGING_OPERATION_NAME: "tests.celery_test_tasks.task_sleep",
                        MESSAGING_CLIENT_ID: self.WORKER_NODE,
                    },
                ),
            ],
            est_value_delta=0.05,
        )

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

    def test_exported_metrics(self):
        """
        Test that number of exported metrics and metrics attributes are as
        expected
        """

        CeleryInstrumentor().instrument()

        expected_attributes = {
            MESSAGING_OPERATION_NAME: "tests.celery_test_tasks.task_add",
            MESSAGING_CLIENT_ID: self.WORKER_NODE,
        }

        self.wait_for_metrics_until_finished(task_add)

        metrics = self.get_sorted_metrics()

        self.assertEqual(len(metrics), EXPECTED_METRICS)
        for metric in metrics:
            for data_point in metric.data.data_points:
                self.assertEqual(
                    expected_attributes,
                    (dict(data_point.attributes)),
                )

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

    def test_uninstrument_metrics(self):
        """
        Even after memory exporter gets cleared, it is still returning metrics,
        so this just checks that subscribers are disconnected from Celery
        events.
        """

        CeleryInstrumentor().instrument()
        self.wait_for_metrics_until_finished(task_add)

        self.assertEqual(len(task_prerun.receivers), 1)
        self.assertEqual(len(task_received.receivers), 1)
        self.assertEqual(len(task_postrun.receivers), 1)

        self.memory_exporter.clear()
        CeleryInstrumentor().uninstrument()

        time.sleep(1)
        task_add.delay()
        time.sleep(1)

        self.assertEqual(len(task_prerun.receivers), 0)
        self.assertEqual(len(task_received.receivers), 0)
        self.assertEqual(len(task_postrun.receivers), 0)

    def test_no_memory_leak_because_of_time_tracking(self):
        """
        To test that time tracking helper class does not keep references to a
        finished task indefinitely
        """

        celery_instrumentor = CeleryInstrumentor()
        celery_instrumentor.instrument()

        for _ in range(5):
            task_add.delay()

        self.wait_for_tasks_to_finish()

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(len(exported_metrics), EXPECTED_METRICS)

        self.assertEqual(len(celery_instrumentor.time_tracker.tracker), 0)

        self.memory_exporter.clear()
        celery_instrumentor.uninstrument()


class TestDurationTracker(TestBase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self.caplog = caplog  # pylint: disable=attribute-defined-outside-init

    def test_duration_tracker(self):
        metrics = _create_celery_worker_metrics(get_meter(self.meter_provider))
        sample_hist_metric = _TASK_PROCESSING_TIME

        tracker = TaskDurationTracker(metrics)
        tracker.record_start("task-id-123", sample_hist_metric)

        # Robustness to undefined keys
        with self.caplog.at_level(logging.WARNING):
            tracker.record_finish("task-id-456", sample_hist_metric, {})
            self.assertIn("Failed to record", self.caplog.text)

        with self.caplog.at_level(logging.WARNING):
            tracker.record_finish("task-id-123", "non_existent_metric", {})
            self.assertIn("Failed to record", self.caplog.text)

        tracker.record_finish("task-id-123", sample_hist_metric, {})

        exported_metrics = self.get_sorted_metrics()
        self.assertEqual(exported_metrics[0].data.data_points[0].count, 1)
