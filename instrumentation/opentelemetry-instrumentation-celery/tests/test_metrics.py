from __future__ import annotations

import threading
import time
from platform import python_implementation
from timeit import default_timer
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from celery.worker.request import Request
from pytest import mark

from opentelemetry.instrumentation.celery import (
    CeleryInstrumentor,
    CeleryWorkerInstrumentor,
    _retrieve_task_name,
    _retrieve_worker_name,
)
from opentelemetry.test.test_base import TestBase

from .celery_test_tasks import app, task_add

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics.export import Metric

SCOPE = "opentelemetry.instrumentation.celery"


def _find_metric(metrics: list[Metric], name: str) -> Metric | None:
    """Find a metric by name in the list of metrics."""
    for metric in metrics:
        if metric.name == name:
            return metric
    return None


def _make_request(task_id: str = "test-id-123", hostname: str = "celery@test"):
    """Create a minimal celery Request for testing."""
    msg = MagicMock()
    msg.headers = {"id": task_id, "task": task_add.name}
    msg.payload = (
        [],
        {},
        {
            "callbacks": None,
            "errbacks": None,
            "chain": None,
            "chord": None,
        },
    )
    msg.delivery_info = {}
    msg.properties = {}
    return Request(msg, app=app, hostname=hostname, task=task_add)


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
        return self.get_sorted_metrics(SCOPE)

    def test_basic_metric(self):
        """Executing a task should record a task runtime histogram."""
        CeleryInstrumentor().instrument()
        start_time = default_timer()
        task_runtime_estimated = (default_timer() - start_time) * 1000

        metrics = self.get_metrics()
        CeleryInstrumentor().uninstrument()

        task_runtime = _find_metric(metrics, "flower.task.runtime.seconds")
        self.assertIsNotNone(task_runtime)
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
        """After uninstrument, no new metric data points should be recorded."""
        CeleryInstrumentor().instrument()

        metrics = self.get_metrics()
        task_runtime = _find_metric(metrics, "flower.task.runtime.seconds")
        self.assertIsNotNone(task_runtime)
        self.assertEqual(
            task_runtime.data.data_points[0].bucket_counts[1],
            1,
        )

        metrics = self.get_metrics()
        task_runtime = _find_metric(metrics, "flower.task.runtime.seconds")
        self.assertIsNotNone(task_runtime)
        self.assertEqual(
            task_runtime.data.data_points[0].bucket_counts[1],
            2,
        )

        CeleryInstrumentor().uninstrument()

        metrics = self.get_metrics()
        task_runtime = _find_metric(metrics, "flower.task.runtime.seconds")
        self.assertIsNotNone(task_runtime)
        self.assertEqual(
            task_runtime.data.data_points[0].bucket_counts[1],
            2,
        )


class TestMetricsIntegration(TestBase):
    """End-to-end integration tests: real worker, real task, full signal chain."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()
        self.worker_instrumentor = CeleryWorkerInstrumentor()
        self.worker_instrumentor.instrument()
        self._worker = app.Worker(
            app=app, pool="solo", concurrency=1, hostname="celery@e2e"
        )
        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        self._worker.stop()
        self._thread.join()
        self.instrumentor.uninstrument()
        self.worker_instrumentor.uninstrument()
        super().tearDown()

    @staticmethod
    def _run_task():
        """Execute task_add through a real worker and wait for completion."""
        result = task_add.delay(1, 2)
        timeout = time.time() + 60
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)
        return result

    def test_events_total_recorded(self):
        """A completed task should record task-sent, task-received, task-started, task-succeeded events."""
        self._run_task()
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)

        recorded_types = {
            dp.attributes["type"] for dp in events.data.data_points
        }
        for expected in (
            "task-sent",
            "task-received",
            "task-started",
            "task-succeeded",
        ):
            self.assertIn(
                expected,
                recorded_types,
                f"Expected event type '{expected}' not found in {recorded_types}",
            )

    def test_task_runtime_histogram_recorded(self):
        """A completed task should produce a flower.task.runtime.seconds histogram."""
        self._run_task()
        metrics = self.get_sorted_metrics(SCOPE)
        runtime = _find_metric(metrics, "flower.task.runtime.seconds")
        self.assertIsNotNone(runtime)
        self.assertGreater(len(runtime.data.data_points), 0)

    def test_executing_tasks_gauge_returns_to_zero(self):
        """After task completes, executing gauge should be back to zero."""
        self._run_task()
        metrics = self.get_sorted_metrics(SCOPE)
        executing = _find_metric(
            metrics, "flower.worker.number.of.currently.executing.tasks"
        )
        self.assertIsNotNone(executing)
        self.assertEqual(executing.data.data_points[0].value, 0)

    def test_metric_attributes_contain_task_and_worker(self):
        """Event metrics should carry both task and worker attributes."""
        self._run_task()
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)

        # Check a data point that should have both task and worker (e.g. task-started)
        started = [
            dp
            for dp in events.data.data_points
            if dp.attributes.get("type") == "task-started"
        ]
        self.assertEqual(len(started), 1)
        self.assertEqual(
            started[0].attributes["task"],
            "tests.celery_test_tasks.task_add",
        )
        self.assertEqual(started[0].attributes["worker"], "celery@e2e")


class TestWorkerMetricsIntegration(TestBase):
    """End-to-end integration tests for CeleryWorkerInstrumentor with a real worker."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryWorkerInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_worker_online_on_start(self):
        """Starting a real worker should set flower.worker.online to 1."""
        worker = app.Worker(
            app=app, pool="solo", concurrency=1, hostname="celery@e2e-worker"
        )
        thread = threading.Thread(target=worker.start)
        thread.daemon = True
        thread.start()

        # Give the worker time to emit worker_ready signal
        time.sleep(0.5)

        metrics = self.get_sorted_metrics(SCOPE)
        worker_online = _find_metric(metrics, "flower.worker.online")
        self.assertIsNotNone(worker_online)
        dp = worker_online.data.data_points[0]
        self.assertEqual(dp.value, 1)
        self.assertEqual(dp.attributes["worker"], "celery@e2e-worker")

        worker.stop()
        thread.join()

    def test_worker_offline_on_stop(self):
        """Stopping a real worker should set flower.worker.online back to 0."""
        worker = app.Worker(
            app=app, pool="solo", concurrency=1, hostname="celery@e2e-worker2"
        )
        thread = threading.Thread(target=worker.start)
        thread.daemon = True
        thread.start()

        time.sleep(0.5)
        worker.stop()
        thread.join()

        metrics = self.get_sorted_metrics(SCOPE)
        worker_online = _find_metric(metrics, "flower.worker.online")
        self.assertIsNotNone(worker_online)
        self.assertEqual(worker_online.data.data_points[0].value, 0)


class TestWorkerMetrics(TestBase):
    """Tests for CeleryWorkerInstrumentor worker lifecycle metrics."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryWorkerInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_worker_ready_increments_online(self):
        """Worker ready signal should increment flower.worker.online gauge."""
        sender = type("Sender", (), {"hostname": "celery@worker1"})()
        self.instrumentor._trace_worker_ready(sender=sender)

        metrics = self.get_sorted_metrics(SCOPE)
        worker_online = _find_metric(metrics, "flower.worker.online")
        self.assertIsNotNone(worker_online)
        self.assertEqual(len(worker_online.data.data_points), 1)
        self.assertEqual(worker_online.data.data_points[0].value, 1)
        self.assertEqual(
            dict(worker_online.data.data_points[0].attributes),
            {"worker": "celery@worker1"},
        )

    def test_worker_ready_idempotent(self):
        """Duplicate worker ready signals should not double-count."""
        sender = type("Sender", (), {"hostname": "celery@worker1"})()
        self.instrumentor._trace_worker_ready(sender=sender)
        self.instrumentor._trace_worker_ready(sender=sender)

        metrics = self.get_sorted_metrics(SCOPE)
        worker_online = _find_metric(metrics, "flower.worker.online")
        self.assertIsNotNone(worker_online)
        # Still 1 — second call was a no-op
        self.assertEqual(worker_online.data.data_points[0].value, 1)

    def test_worker_shutdown_decrements_online(self):
        """Worker shutdown should decrement the online gauge back to zero."""
        sender = type("Sender", (), {"hostname": "celery@worker1"})()
        self.instrumentor._trace_worker_ready(sender=sender)
        self.instrumentor._trace_worker_shutdown(sender=sender)

        metrics = self.get_sorted_metrics(SCOPE)
        worker_online = _find_metric(metrics, "flower.worker.online")
        self.assertIsNotNone(worker_online)
        self.assertEqual(worker_online.data.data_points[0].value, 0)

    def test_worker_shutdown_unknown_worker_noop(self):
        """Shutdown for an unknown worker should not raise or record anything."""
        sender = type("Sender", (), {"hostname": "celery@unknown"})()
        self.instrumentor._trace_worker_shutdown(sender=sender)

        metrics = self.get_sorted_metrics(SCOPE)
        worker_online = _find_metric(metrics, "flower.worker.online")
        # No data points recorded
        self.assertTrue(
            worker_online is None or len(worker_online.data.data_points) == 0
        )

    def test_uninstrument_disconnects_signals(self):
        """Uninstrumenting should disconnect signals and reset state."""
        sender = type("Sender", (), {"hostname": "celery@test-disconnect"})()
        self.instrumentor._trace_worker_ready(sender=sender)
        self.assertIn(
            "celery@test-disconnect", self.instrumentor.online_workers
        )

        # Uninstrument and verify signal no longer fires our handler
        self.instrumentor.uninstrument()

        # Re-instrument to check the signal was truly disconnected
        # (online_workers was reset)
        self.instrumentor.instrument()
        self.assertNotIn(
            "celery@test-disconnect", self.instrumentor.online_workers
        )


class TestTaskReceivedMetrics(TestBase):
    """Tests for _trace_task_received signal handler and its metric side-effects."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryWorkerInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_task_received_records_event(self):
        """Firing task_received should increment events_total."""
        request = _make_request(task_id="rcv-1", hostname="celery@w1")
        sender = type("Sender", (), {"hostname": "celery@w1"})()

        self.instrumentor._trace_task_received(request=request, sender=sender)

        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)
        self.assert_metric_expected(
            events,
            [
                self.create_number_data_point(
                    value=1,
                    attributes={
                        "task": task_add.name,
                        "type": "task-received",
                        "worker": "celery@w1",
                    },
                )
            ],
        )

    def test_task_received_invalid_request_is_noop(self):
        """Non-Request objects should be silently ignored."""
        self.instrumentor._trace_task_received(request=None, sender=None)
        self.instrumentor._trace_task_received(
            request="not-a-request", sender=None
        )

        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)


class TestTaskRevokedMetrics(TestBase):
    """Tests for _trace_task_revoked signal handler."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryWorkerInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_task_revoked_records_event(self):
        """Revoking a task should record a task-revoked event."""
        request = _make_request(task_id="rev-1", hostname="celery@w1")
        sender = type("Sender", (), {"hostname": "celery@w1"})()

        self.instrumentor._trace_task_revoked(request=request, sender=sender)

        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)
        self.assert_metric_expected(
            events,
            [
                self.create_number_data_point(
                    value=1,
                    attributes={
                        "task": task_add.name,
                        "type": "task-revoked",
                        "worker": "celery@w1",
                    },
                )
            ],
        )

    def test_task_revoked_invalid_request_is_noop(self):
        """Non-Request objects should be silently ignored."""
        self.instrumentor._trace_task_revoked(request=None, sender=None)

        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)


class TestRetrieveTaskName(TestBase):
    """Tests for the _retrieve_task_name helper function."""

    def test_from_task_name(self):
        """Task with a name attribute should return that name."""
        task = type("Task", (), {"name": "my.task"})()
        self.assertEqual(_retrieve_task_name(task=task), "my.task")

    def test_from_request_task_object_with_name(self):
        """Request.task as an object with .name should be used."""
        inner_task = type("Task", (), {"name": "inner.task"})()
        request = type("Request", (), {"task": inner_task, "name": None})()
        self.assertEqual(_retrieve_task_name(request=request), "inner.task")

    def test_from_request_task_string(self):
        """Request.task as a string should be returned directly."""
        request = type("Request", (), {"task": "string.task", "name": None})()
        self.assertEqual(_retrieve_task_name(request=request), "string.task")

    def test_from_request_name(self):
        """Request.name should be used as fallback when task is None."""
        request = type("Request", (), {"task": None, "name": "req.name"})()
        self.assertEqual(_retrieve_task_name(request=request), "req.name")

    def test_returns_none_when_no_info(self):
        """No arguments or a task with name=None should return None."""
        self.assertIsNone(_retrieve_task_name())
        self.assertIsNone(
            _retrieve_task_name(task=type("T", (), {"name": None})())
        )


class TestRetrieveWorkerName(TestBase):
    """Tests for the _retrieve_worker_name helper function."""

    def test_from_task_request_hostname(self):
        """task.request.hostname should be preferred source."""
        inner_req = type("Req", (), {"hostname": "celery@from-task"})()
        task = type("Task", (), {"request": inner_req})()
        self.assertEqual(_retrieve_worker_name(task=task), "celery@from-task")

    def test_from_request_hostname(self):
        """Request object hostname should be used when no task is given."""
        request = _make_request(hostname="celery@from-req")
        self.assertEqual(
            _retrieve_worker_name(request=request), "celery@from-req"
        )

    def test_from_sender_hostname(self):
        """Sender hostname should be used as last resort."""
        sender = type("Sender", (), {"hostname": "celery@from-sender"})()
        self.assertEqual(
            _retrieve_worker_name(sender=sender), "celery@from-sender"
        )

    def test_returns_none_when_no_info(self):
        """No arguments or sender without hostname should return None."""
        self.assertIsNone(_retrieve_worker_name())
        self.assertIsNone(_retrieve_worker_name(sender=type("S", (), {})()))
