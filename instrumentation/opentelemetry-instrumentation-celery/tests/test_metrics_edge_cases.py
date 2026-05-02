from __future__ import annotations

from timeit import default_timer
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from billiard.einfo import ExceptionInfo
from celery.worker.request import Request

from opentelemetry.instrumentation.celery import (
    CeleryInstrumentor,
    CeleryWorkerInstrumentor,
    utils,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace.status import StatusCode

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


class TestMetricsNotInitialized(TestBase):
    """Tests for error paths when metrics are not initialized."""

    def test_task_metrics_raises_before_instrument(self):
        """Accessing _metrics() before instrument() should raise RuntimeError."""
        instrumentor = CeleryInstrumentor()
        instrumentor.metrics = None
        with self.assertRaises(RuntimeError):
            instrumentor._metrics()

    def test_worker_metrics_raises_before_instrument(self):
        """Accessing _worker_metrics() before instrument() should raise RuntimeError."""
        instrumentor = CeleryWorkerInstrumentor()
        instrumentor.metrics = None
        with self.assertRaises(RuntimeError):
            instrumentor._worker_metrics()


class TestRecordEventCountGuards(TestBase):
    """Tests for _record_event_count early-return when task_name is None."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_record_event_count_none_task_name_is_noop(self):
        """None task_name should cause an early return with no metric recorded."""
        self.instrumentor._record_event_count("task-received", task_name=None)
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)

    def test_record_event_count_without_worker(self):
        """Event should be recorded without worker attribute when worker is None."""
        self.instrumentor._record_event_count(
            "task-sent", task_name="my.task", worker=None
        )
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)
        self.assert_metric_expected(
            events,
            [
                self.create_number_data_point(
                    value=1,
                    attributes={"task": "my.task", "type": "task-sent"},
                )
            ],
        )


class TestTrackingGuards(TestBase):
    """Tests for guard paths in track/untrack helpers."""

    def setUp(self):
        super().setUp()
        self.task_instrumentor = CeleryInstrumentor()
        self.task_instrumentor.instrument()
        self.worker_instrumentor = CeleryWorkerInstrumentor()
        self.worker_instrumentor.instrument()

    def tearDown(self):
        self.task_instrumentor.uninstrument()
        self.worker_instrumentor.uninstrument()
        super().tearDown()

    def test_track_executing_task_none_args_is_noop(self):
        """None task_id or worker should cause an early return."""
        self.task_instrumentor._track_executing_task(None, "worker")
        self.task_instrumentor._track_executing_task("id", None)
        self.assertEqual(
            len(self.task_instrumentor.executing_task_id_to_worker), 0
        )

    def test_untrack_executing_task_unknown_id_is_noop(self):
        """Untracking an unknown task_id should not raise or record."""
        self.task_instrumentor._untrack_executing_task("nonexistent-id")
        metrics = self.get_sorted_metrics(SCOPE)
        executing = _find_metric(
            metrics, "flower.worker.number.of.currently.executing.tasks"
        )
        self.assertTrue(
            executing is None or len(executing.data.data_points) == 0
        )

    def test_record_histograms_none_task_id_is_noop(self):
        """None task_id should skip histogram recording."""
        self.task_instrumentor._record_histograms(
            None, {"task": "t", "worker": "w"}
        )
        metrics = self.get_sorted_metrics(SCOPE)
        runtime = _find_metric(metrics, "flower.task.runtime.seconds")
        self.assertTrue(runtime is None or len(runtime.data.data_points) == 0)


class TestTraceRetry(TestBase):
    """Tests for _trace_retry signal handler."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def _setup_task_with_span(self):
        """Create a task with an attached span context, as _trace_retry expects."""
        task = task_add
        task_id = "retry-1"
        tracer = self.tracer_provider.get_tracer("test")
        span = tracer.start_span("test")
        activation = MagicMock()
        activation.__enter__ = MagicMock(return_value=span)
        activation.__exit__ = MagicMock(return_value=False)
        utils.attach_context(task, task_id, span, activation, None)
        return task, task_id, span

    def test_trace_retry_records_reason_and_event(self):
        """Retry with attached span should set reason attribute and record event."""
        task, task_id, span = self._setup_task_with_span()
        request = type("Request", (), {"id": task_id})()

        self.instrumentor._trace_retry(
            sender=task,
            task_id=task_id,
            request=request,
            reason=Exception("connection lost"),
        )

        self.assertTrue(span.is_recording())
        self.assertEqual(
            span.attributes.get("celery.retry.reason"), "connection lost"
        )

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
                        "type": "task-retried",
                    },
                )
            ],
        )
        # cleanup
        utils.detach_context(task, task_id)

    def test_trace_retry_no_task_is_noop(self):
        """Retry with no sender/task should be silently ignored."""
        self.instrumentor._trace_retry(
            sender=None, task_id=None, request=None, reason=None
        )
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)

    def test_trace_retry_no_context_is_noop(self):
        """If no span context is attached, retry should bail out silently."""
        request = type("Request", (), {"id": "no-ctx"})()
        self.instrumentor._trace_retry(
            sender=task_add,
            request=request,
            reason=Exception("retry"),
        )
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)


class TestTracePrerunPostrunGuards(TestBase):
    """Tests for early-return guards in _trace_prerun and _trace_postrun."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_prerun_no_task_is_noop(self):
        """Prerun with no task should produce no spans."""
        self.instrumentor._trace_prerun(task=None, task_id=None)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_postrun_no_task_is_noop(self):
        """Postrun with no task should produce no spans."""
        self.instrumentor._trace_postrun(task=None, task_id=None)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_postrun_no_context_is_noop(self):
        """When no span was attached, postrun should log and return."""
        self.instrumentor._trace_postrun(task=task_add, task_id="no-ctx")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)


class TestTracePostrunStateMetrics(TestBase):
    """Tests for postrun event counting based on task state."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def _attach_context_to_task(self, task, task_id: str):
        """Attach a live span context to a task for postrun tests."""
        tracer = self.tracer_provider.get_tracer("test")
        span = tracer.start_span("test")
        activation = MagicMock()
        activation.__enter__ = MagicMock(return_value=span)
        activation.__exit__ = MagicMock(return_value=False)
        utils.attach_context(task, task_id, span, activation, None)

    def test_postrun_records_task_succeeded_only_for_success_state(self):
        """Postrun should record task-succeeded when the task state is SUCCESS."""
        task_id = "postrun-success"
        request = type(
            "RequestContext",
            (dict,),
            {"hostname": "celery@w1", "state": "SUCCESS"},
        )({})
        task = type("Task", (), {"name": task_add.name, "request": request})()
        self.instrumentor.task_id_to_start_time[task_id] = default_timer()
        self.instrumentor._track_executing_task(task_id, "celery@w1")
        self._attach_context_to_task(task, task_id)

        self.instrumentor._trace_postrun(task=task, task_id=task_id)

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
                        "type": "task-succeeded",
                        "worker": "celery@w1",
                    },
                )
            ],
        )

    def test_postrun_skips_task_succeeded_for_non_success_state(self):
        """Postrun should not record task-succeeded when the task state is not SUCCESS."""
        task_id = "postrun-failure"
        request = type(
            "RequestContext",
            (dict,),
            {"hostname": "celery@w1", "state": "FAILURE"},
        )({})
        task = type("Task", (), {"name": task_add.name, "request": request})()
        self.instrumentor.task_id_to_start_time[task_id] = default_timer()
        self.instrumentor._track_executing_task(task_id, "celery@w1")
        self._attach_context_to_task(task, task_id)

        self.instrumentor._trace_postrun(task=task, task_id=task_id)

        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)


class TestTracePublishGuards(TestBase):
    """Tests for guard paths in _trace_before_publish and _trace_after_publish."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_before_publish_no_task_id_is_noop(self):
        """Before publish with no task ID in headers should produce no spans."""
        self.instrumentor._trace_before_publish(
            sender=None, headers={}, body=None
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_before_publish_anonymous_task(self):
        """When task is not found in registry, sender string is used as name."""
        self.instrumentor._trace_before_publish(
            sender="some.unknown.task",
            headers={"id": "pub-1"},
            body=None,
        )
        # Span started but not finished (no after_publish called)
        # Verify via event count instead
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)
        self.assert_metric_expected(
            events,
            [
                self.create_number_data_point(
                    value=1,
                    attributes={
                        "task": "some.unknown.task",
                        "type": "task-sent",
                    },
                )
            ],
        )

    def test_after_publish_no_task_is_noop(self):
        """After publish with no sender should produce no spans."""
        CeleryInstrumentor._trace_after_publish(
            sender=None, headers={}, body=None
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_after_publish_no_context_is_noop(self):
        """When no span was attached, after_publish should log and return."""
        CeleryInstrumentor._trace_after_publish(
            sender=task_add, headers={"id": "missing-ctx"}, body=None
        )
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)


class TestTraceFailureGuards(TestBase):
    """Tests for guard paths in _trace_failure."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_failure_no_task_is_noop(self):
        """Failure with no sender should not record any events."""
        self.instrumentor._trace_failure(sender=None, task_id=None, einfo=None)
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)

    def test_failure_no_context_is_noop(self):
        """Failure with no attached span context should not record events."""
        self.instrumentor._trace_failure(
            sender=task_add, task_id="no-ctx", einfo=None
        )
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)

    def test_failure_not_recording_is_noop(self):
        """When span is not recording, failure should bail."""
        span = MagicMock()
        span.is_recording.return_value = False
        activation = MagicMock()
        utils.attach_context(task_add, "nr-1", span, activation, None)

        self.instrumentor._trace_failure(
            sender=task_add, task_id="nr-1", einfo=None
        )
        span.set_status.assert_not_called()
        utils.detach_context(task_add, "nr-1")

    def test_failure_task_throws_skipped(self):
        """Exceptions listed in task.throws should not be recorded."""
        tracer = self.tracer_provider.get_tracer("test")
        span = tracer.start_span("test")
        activation = MagicMock()
        activation.__enter__ = MagicMock(return_value=span)
        activation.__exit__ = MagicMock(return_value=False)

        task = task_add
        task_id = "throws-1"
        # Temporarily set throws
        original_throws = getattr(task, "throws", ())
        task.throws = (ValueError,)
        utils.attach_context(task, task_id, span, activation, None)

        einfo = MagicMock()
        einfo.exception = ValueError("expected")

        self.instrumentor._trace_failure(
            sender=task, task_id=task_id, einfo=einfo
        )
        # Status should NOT be set to ERROR for throws exceptions
        self.assertNotEqual(
            span.status.status_code,
            2,  # StatusCode.ERROR
        )
        utils.detach_context(task, task_id)
        task.throws = original_throws


class TestMemoryLeakPrevention(TestBase):
    """Tests that verify internal state dicts are cleaned up to prevent memory leaks."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def _attach_context_to_task(self, task, task_id: str):
        """Attach a live span context to a task."""
        tracer = self.tracer_provider.get_tracer("test")
        span = tracer.start_span("test")
        activation = MagicMock()
        activation.__enter__ = MagicMock(return_value=span)
        activation.__exit__ = MagicMock(return_value=False)
        utils.attach_context(task, task_id, span, activation, None)

    def test_postrun_cleans_up_start_time(self):
        """After postrun, task_id_to_start_time should not retain the task_id."""
        task_id = "leak-1"
        request = type(
            "RequestContext",
            (dict,),
            {"hostname": "celery@w1", "state": "SUCCESS"},
        )({})
        task = type("Task", (), {"name": task_add.name, "request": request})()
        self.instrumentor.task_id_to_start_time[task_id] = default_timer()
        self._attach_context_to_task(task, task_id)

        self.instrumentor._trace_postrun(task=task, task_id=task_id)

        self.assertNotIn(task_id, self.instrumentor.task_id_to_start_time)


class TestTraceRetryNotRecording(TestBase):
    """Tests for _trace_retry when span is not recording."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_trace_retry_not_recording_is_noop(self):
        """Retry with a non-recording span should not set attributes or record events."""
        span = MagicMock()
        span.is_recording.return_value = False
        activation = MagicMock()
        task_id = "retry-nr"
        utils.attach_context(task_add, task_id, span, activation, None)
        request = type("Request", (), {"id": task_id})()

        self.instrumentor._trace_retry(
            sender=task_add,
            request=request,
            reason=Exception("retry reason"),
        )

        span.set_attribute.assert_not_called()
        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertTrue(events is None or len(events.data.data_points) == 0)

        utils.detach_context(task_add, task_id)


class TestTraceFailureRecordsEvent(TestBase):
    """Tests for _trace_failure happy path — exception recorded and event counted."""

    def setUp(self):
        super().setUp()
        self.instrumentor = CeleryInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        self.instrumentor.uninstrument()
        super().tearDown()

    def test_failure_records_exception_and_event(self):
        """A genuine failure should set ERROR status and record a task-failed event."""
        tracer = self.tracer_provider.get_tracer("test")
        span = tracer.start_span("test")
        activation = MagicMock()
        activation.__enter__ = MagicMock(return_value=span)
        activation.__exit__ = MagicMock(return_value=False)
        task_id = "fail-1"
        utils.attach_context(task_add, task_id, span, activation, None)

        einfo = None
        try:
            raise RuntimeError("something broke")
        except RuntimeError:
            einfo = ExceptionInfo()

        self.instrumentor._trace_failure(
            sender=task_add, task_id=task_id, einfo=einfo
        )

        self.assertEqual(span.status.status_code, StatusCode.ERROR)

        metrics = self.get_sorted_metrics(SCOPE)
        events = _find_metric(metrics, "flower.events.total")
        self.assertIsNotNone(events)
        recorded_types = {
            dp.attributes["type"] for dp in events.data.data_points
        }
        self.assertIn("task-failed", recorded_types)

        utils.detach_context(task_add, task_id)


class TestUninstrumentClearsState(TestBase):
    """Tests that uninstrument resets all internal state."""

    def test_uninstrument_clears_task_instrumentor_state(self):
        """After uninstrument, all tracking dicts and metrics should be reset."""
        instrumentor = CeleryInstrumentor()
        instrumentor.instrument()

        # Simulate some accumulated state
        instrumentor.task_id_to_start_time["t1"] = 1.0
        instrumentor.executing_task_id_to_worker["t1"] = "celery@w"

        instrumentor.uninstrument()

        self.assertIsNone(instrumentor.metrics)
        self.assertEqual(instrumentor.task_id_to_start_time, {})
        self.assertEqual(instrumentor.executing_task_id_to_worker, {})

    def test_uninstrument_clears_worker_instrumentor_state(self):
        """After uninstrument, online_workers, tracking dicts, and metrics should be reset."""
        instrumentor = CeleryWorkerInstrumentor()
        instrumentor.instrument()

        instrumentor.online_workers.add("celery@w1")

        instrumentor.uninstrument()

        self.assertIsNone(instrumentor.metrics)
        self.assertEqual(instrumentor.online_workers, set())
