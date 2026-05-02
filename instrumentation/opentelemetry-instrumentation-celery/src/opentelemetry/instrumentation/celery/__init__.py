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
"""
Instrument `celery`_ to trace Celery applications.

.. _celery: https://pypi.org/project/celery/

Usage
-----

* Start broker backend

.. code::

    docker run -p 5672:5672 rabbitmq


* Run instrumented task

.. code:: python

    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    from celery import Celery
    from celery.signals import worker_process_init

    @worker_process_init.connect(weak=False)
    def init_celery_tracing(*args, **kwargs):
        CeleryInstrumentor().instrument()

    app = Celery("tasks", broker="amqp://localhost")

    @app.task
    def add(x, y):
        return x + y

    add.delay(42, 50)

Setting up tracing
------------------

When tracing a celery worker process, tracing and instrumentation both must be initialized after the celery worker
process is initialized. This is required for any tracing components that might use threading to work correctly
such as the BatchSpanProcessor. Celery provides a signal called ``worker_process_init`` that can be used to
accomplish this as shown in the example above.

Worker-level metrics
--------------------

To collect worker lifecycle metrics (online/offline status), use
``CeleryWorkerInstrumentor`` in the **main worker process** via the
``celeryd_after_setup`` signal.  This signal fires before
``worker_ready``, ensuring the handler is connected in time.

.. code:: python

    from opentelemetry.instrumentation.celery import (
        CeleryInstrumentor,
        CeleryWorkerInstrumentor,
    )
    from celery.signals import celeryd_after_setup, worker_process_init

    @celeryd_after_setup.connect(weak=False)
    def init_worker_metrics(sender, instance, conf, **kwargs):
        CeleryWorkerInstrumentor().instrument()

    @worker_process_init.connect(weak=False)
    def init_celery_tracing(*args, **kwargs):
        CeleryInstrumentor().instrument()

API
---
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from timeit import default_timer
from typing import TYPE_CHECKING, Any, Optional, cast

from billiard import VERSION
from billiard.einfo import ExceptionInfo
from celery import signals  # pylint: disable=import-self
from celery import (
    states as celery_states,  # pylint: disable=import-self, no-name-in-module
)
from celery.worker.request import Request  # pylint: disable=no-name-in-module

from opentelemetry import context as context_api
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.celery import utils
from opentelemetry.instrumentation.celery.package import _instruments
from opentelemetry.instrumentation.celery.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.metrics import get_meter
from opentelemetry.propagate import extract, inject
from opentelemetry.propagators.textmap import Getter
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
)
from opentelemetry.trace.status import Status, StatusCode

if TYPE_CHECKING:
    from celery.app.task import Task

    from opentelemetry.metrics import Counter, Histogram, Meter, UpDownCounter
if VERSION >= (4, 0, 1):
    from billiard.einfo import ExceptionWithTraceback
else:
    ExceptionWithTraceback = None

logger = logging.getLogger(__name__)

# Task operations
_TASK_TAG_KEY = "celery.action"
_TASK_APPLY_ASYNC = "apply_async"
_TASK_RUN = "run"

_TASK_RETRY_REASON_KEY = "celery.retry.reason"
_TASK_NAME_KEY = "celery.task_name"


class CeleryGetter(Getter[Request]):
    def get(self, carrier: "Request", key: str) -> list[str] | None:
        value = getattr(carrier, key, None)
        if value is None:
            return None
        # Celery's Context copies all message properties as instance
        # attributes, including non-string values like timelimit (tuple
        # of ints).  The TextMapPropagator contract requires string
        # values, so coerce anything that isn't already a string.
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            return [str(v) if not isinstance(v, str) else v for v in value]
        return [str(value)]

    def keys(self, carrier: "Request") -> list[str]:
        return []


celery_getter = CeleryGetter()


def _log_signal(
    signal_name: str,
    task_id: Optional[str] = None,
    task_name: Optional[str] = None,
    worker: Optional[str] = None,
) -> None:
    """Log Celery signal execution context."""
    logger.debug(
        "%s signal received task_id=%s task_name=%s worker=%s",
        signal_name,
        task_id,
        task_name,
        worker,
    )


def _retrieve_task_name(
    task: "Optional[Task]" = None,
    request: "Optional[Request]" = None,
) -> "Optional[str]":
    """Retrieve the task name from the task or request objects."""
    if task is not None and getattr(task, "name", None) is not None:
        return task.name
    if request is not None:
        request_task = getattr(request, "task", None)
        if request_task is not None:
            # request.task may be a Task object or a string name
            if hasattr(request_task, "name"):
                return request_task.name
            return str(request_task)
        request_name = getattr(request, "name", None)
        if request_name is not None:
            return str(request_name)
    return None


def _retrieve_worker_name(
    task: "Optional[Task]" = None,
    request: "Optional[Request]" = None,
    sender: Optional[object] = None,
) -> Optional[str]:
    """Retrieve the worker name from the task, request, or sender objects."""
    task_request = task.request if task is not None else None
    if task_request is not None:
        task_request_worker = getattr(task_request, "hostname", None)
        if task_request_worker is not None:
            return task_request_worker

    if request is not None:
        request_worker = cast(
            Optional[str], getattr(request, "hostname", None)
        )
        if request_worker is not None:
            return request_worker

    if sender is not None:
        return cast(Optional[str], getattr(sender, "hostname", None))
    return None


@dataclass(frozen=True)
class _CeleryTaskMetricNames:
    """Canonical metric names for Celery task instrumentation."""

    events_total: str = "flower.events.total"
    task_runtime_seconds: str = "flower.task.runtime.seconds"
    worker_currently_executing_tasks: str = (
        "flower.worker.number.of.currently.executing.tasks"
    )


@dataclass(frozen=True)
class _CeleryWorkerMetricNames:
    """Canonical metric names for Celery worker lifecycle instrumentation."""

    events_total: str = "flower.events.total"
    worker_online: str = "flower.worker.online"


_TASK_METRIC_NAMES = _CeleryTaskMetricNames()
_WORKER_METRIC_NAMES = _CeleryWorkerMetricNames()


@dataclass(frozen=True)
class _CeleryEventTypes:
    """Celery event type identifiers used as metric label values."""

    task_sent: str = "task-sent"
    task_received: str = "task-received"
    task_started: str = "task-started"
    task_succeeded: str = "task-succeeded"
    task_failed: str = "task-failed"
    task_retried: str = "task-retried"
    task_revoked: str = "task-revoked"


_EVENT_TYPES = _CeleryEventTypes()


@dataclass
class CeleryTaskMetrics:
    """Metrics for tracking Celery task events and states."""

    events_total: "Counter"
    task_runtime_seconds: "Histogram"
    worker_currently_executing_tasks: "UpDownCounter"


@dataclass
class CeleryWorkerMetrics:
    """Metrics for tracking Celery worker lifecycle."""

    events_total: "Counter"
    worker_online: "UpDownCounter"


class CeleryInstrumentor(BaseInstrumentor):
    """An instrumentor for Celery task execution.

    Traces task publish, run, failure, retry, and revocation.
    Tracks task-level metrics (event counts, runtime,
    currently executing tasks).

    Must be initialized in the worker subprocess via the
    ``worker_process_init`` signal."""

    def __init__(self) -> None:
        super().__init__()
        self.metrics: Optional[CeleryTaskMetrics] = None
        self.task_id_to_start_time: dict = {}
        self.executing_task_id_to_worker: dict = {}

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: object) -> None:
        """Connect Celery signal handlers and create task-level metrics."""
        tracer_provider = cast(
            Optional[trace.TracerProvider], kwargs.get("tracer_provider")
        )

        # pylint: disable=attribute-defined-outside-init
        self._tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        meter_provider = cast(
            Optional[metrics.MeterProvider], kwargs.get("meter_provider")
        )
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        self.task_id_to_start_time = {}
        self.executing_task_id_to_worker = {}

        self.metrics = self.create_task_metrics(meter)

        # Connect signal handlers to trace Celery events and track task states
        signals.task_prerun.connect(self._trace_prerun, weak=False)
        signals.task_postrun.connect(self._trace_postrun, weak=False)
        signals.before_task_publish.connect(
            self._trace_before_publish, weak=False
        )
        signals.after_task_publish.connect(
            self._trace_after_publish, weak=False
        )
        signals.task_failure.connect(self._trace_failure, weak=False)
        signals.task_retry.connect(self._trace_retry, weak=False)

    def _uninstrument(self, **kwargs: object) -> None:
        """Uninstrument Celery by disconnecting all signal handlers and clearing metrics and state."""
        signals.task_prerun.disconnect(self._trace_prerun)
        signals.task_postrun.disconnect(self._trace_postrun)
        signals.before_task_publish.disconnect(self._trace_before_publish)
        signals.after_task_publish.disconnect(self._trace_after_publish)
        signals.task_failure.disconnect(self._trace_failure)
        signals.task_retry.disconnect(self._trace_retry)
        self.metrics = None
        self.task_id_to_start_time = {}
        self.executing_task_id_to_worker = {}

    def _metrics(self) -> CeleryTaskMetrics:
        """Retrieve the Celery metrics object, raising an error if not initialized."""
        if self.metrics is not None:
            return self.metrics
        raise RuntimeError("Celery metrics are not initialized")

    def _record_event_count(
        self,
        event_type: str,
        task_name: Optional[str] = None,
        worker: Optional[str] = None,
    ) -> None:
        """Record a Celery event by incrementing the events counter."""
        if task_name is None:
            return

        attributes: dict[str, str] = {
            "task": task_name,
            "type": event_type,
        }
        if worker is not None:
            attributes["worker"] = worker

        self._metrics().events_total.add(
            1,
            attributes=attributes,
        )

    def _track_executing_task(
        self,
        task_id: Optional[str],
        worker: Optional[str],
    ) -> None:
        """Track an executing task by recording its worker and incrementing the executing tasks counter."""
        if task_id is None or worker is None:
            return

        self.executing_task_id_to_worker[task_id] = worker
        self._metrics().worker_currently_executing_tasks.add(
            1,
            attributes={"worker": worker},
        )

    def _untrack_executing_task(self, task_id: str) -> None:
        """Untrack an executing task by removing its worker and decrementing the executing tasks counter."""
        worker = self.executing_task_id_to_worker.pop(task_id, None)
        if worker is None:
            return

        self._metrics().worker_currently_executing_tasks.add(
            -1,
            attributes={"worker": worker},
        )

    def _trace_prerun(self, *args: object, **kwargs: object) -> None:
        """Start a span for a task about to be executed and track the executing task by recording its start time and incrementing the executing tasks counter."""
        task = utils.retrieve_task(kwargs)
        task_id = utils.retrieve_task_id(kwargs)
        task_name = task.name if task is not None else None
        worker = _retrieve_worker_name(task=task) if task is not None else None
        _log_signal("task_prerun", task_id, task_name, worker)

        if task is None or task_id is None:
            return

        self.update_task_duration_time(task_id)
        request = task.request
        tracectx = extract(request, getter=celery_getter) or None
        token = context_api.attach(tracectx) if tracectx is not None else None

        operation_name = f"{_TASK_RUN}/{task.name}"
        span = self._tracer.start_span(
            operation_name, context=tracectx, kind=trace.SpanKind.CONSUMER
        )

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=unnecessary-dunder-call
        utils.attach_context(task, task_id, span, activation, token)

        worker = _retrieve_worker_name(task=task)
        self._track_executing_task(task_id, worker)
        self._record_event_count(_EVENT_TYPES.task_started, task.name, worker)

    def _trace_postrun(self, *args: object, **kwargs: object) -> None:
        """Finish a span for a task that has been executed and untrack the executing task by recording its end time and decrementing the executing tasks counter.

        https://docs.celeryq.dev/en/main/userguide/signals.html#task-postrun
        """
        task = utils.retrieve_task(kwargs)
        task_id = utils.retrieve_task_id(kwargs)
        task_name = task.name if task is not None else None
        worker = _retrieve_worker_name(task=task) if task is not None else None
        _log_signal("task_postrun", task_id, task_name, worker)

        if task is None or task_id is None:
            return

        # retrieve and finish the Span
        ctx = utils.retrieve_context(task, task_id)

        if ctx is None:
            logger.warning("no existing span found for task_id=%s", task_id)
            return

        span, activation, token = ctx

        # Type safety: task.name could be None, but the span attribute requires a string.  In this case we can use "unknown" as a fallback task name for the span attribute since it's better to have an "unknown" task name than to have no span at all.
        task_name = task.name or "unknown"

        # request context tags
        if span.is_recording():
            span.set_attribute(_TASK_TAG_KEY, _TASK_RUN)
            utils.set_attributes_from_context(span, kwargs)
            utils.set_attributes_from_context(span, task.request)
            span.set_attribute(_TASK_NAME_KEY, task_name)

        activation.__exit__(None, None, None)
        utils.detach_context(task, task_id)
        self.update_task_duration_time(task_id)
        task_state = cast(
            Optional[str],
            kwargs.get("state", getattr(task.request, "state", None)),
        )
        labels = {"task": task_name, "worker": task.request.hostname}
        self._record_histograms(task_id, labels)
        self.task_id_to_start_time.pop(task_id, None)
        self._untrack_executing_task(task_id)

        # Update event counts based on task state
        if task_state == celery_states.SUCCESS:
            _log_signal(
                "task_succeeded",
                task_id,
                task_name,
                worker,
            )
            self._record_event_count(
                _EVENT_TYPES.task_succeeded, task_name, task.request.hostname
            )

        # if the process sending the task is not instrumented
        # there's no incoming context and no token to detach
        if token is not None:
            context_api.detach(token)

    def _trace_before_publish(self, *args: object, **kwargs: object) -> None:
        """Start a span for a task about to be published and track the publishing task by recording its start time and incrementing the publishing tasks counter."""
        task = utils.retrieve_task_from_sender(kwargs)
        task_id = utils.retrieve_task_id_from_message(kwargs)
        task_name = task.name if task is not None else None
        _log_signal(
            "before_task_publish",
            task_id,
            task_name,
            None,
        )

        if task_id is None:
            return

        if task is None:
            # task is an anonymous task send using send_task or using canvas workflow
            # Signatures() to send to a task not in the current processes dependency
            # tree
            sender = kwargs.get("sender")
            task_name = str(sender) if sender is not None else "unknown"
        else:
            task_name = task.name or "unknown"
        operation_name = f"{_TASK_APPLY_ASYNC}/{task_name}"
        span = self._tracer.start_span(
            operation_name, kind=trace.SpanKind.PRODUCER
        )

        # apply some attributes here because most of the data is not available
        if span.is_recording():
            span.set_attribute(_TASK_TAG_KEY, _TASK_APPLY_ASYNC)
            span.set_attribute(MESSAGING_MESSAGE_ID, task_id)
            span.set_attribute(_TASK_NAME_KEY, task_name)
            utils.set_attributes_from_context(span, kwargs)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=unnecessary-dunder-call

        utils.attach_context(
            task, task_id, span, activation, None, is_publish=True
        )

        headers = kwargs.get("headers")
        if headers:
            inject(headers)

        self._record_event_count(_EVENT_TYPES.task_sent, task_name, None)

    @staticmethod
    def _trace_after_publish(*args: object, **kwargs: object) -> None:
        """Finish a span for a task that has been published and untrack the publishing task by recording its end time and decrementing the publishing tasks counter."""
        task = utils.retrieve_task_from_sender(kwargs)
        task_id = utils.retrieve_task_id_from_message(kwargs)
        task_name = task.name if task is not None else None
        _log_signal("after_task_publish", task_id, task_name, None)

        if task is None or task_id is None:
            return

        # retrieve and finish the Span
        ctx = utils.retrieve_context(task, task_id, is_publish=True)

        if ctx is None:
            logger.warning("no existing span found for task_id=%s", task_id)
            return

        _, activation, _ = ctx

        activation.__exit__(None, None, None)  # pylint: disable=unnecessary-dunder-call
        utils.detach_context(task, task_id, is_publish=True)

    def _trace_failure(self, *args: object, **kwargs: object) -> None:
        """Trace a task failure event by recording the exception and incrementing the failure event counter."""
        task = utils.retrieve_task_from_sender(kwargs)
        task_id = utils.retrieve_task_id(kwargs)
        task_name = task.name if task is not None else None
        worker = _retrieve_worker_name(task=task) if task is not None else None
        _log_signal("task_failure", task_id, task_name, worker)

        if task is None or task_id is None:
            return

        ctx = utils.retrieve_context(task, task_id)

        if ctx is None:
            return

        span, _, _ = ctx

        if not span.is_recording():
            return

        status_description: Optional[str] = None

        ex = kwargs.get("einfo")

        if (
            hasattr(task, "throws")
            and ex is not None
            and isinstance(ex.exception, task.throws)
        ):
            return

        if ex is not None:
            # Unwrap the actual exception wrapped by billiard's
            # `ExceptionInfo` and `ExceptionWithTraceback`.
            if isinstance(ex, ExceptionInfo) and ex.exception is not None:
                ex = ex.exception

            if (
                ExceptionWithTraceback is not None
                and isinstance(ex, ExceptionWithTraceback)
                and ex.exc is not None
            ):
                ex = ex.exc

            status_description = str(ex)
            span.record_exception(ex)
        span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=status_description,
            )
        )
        worker = _retrieve_worker_name(task=task)
        self._record_event_count(_EVENT_TYPES.task_failed, task.name, worker)

    def _trace_retry(self, *args: object, **kwargs: object) -> None:
        """Trace a task retry event by recording its reason and incrementing the retry event counter."""
        task = utils.retrieve_task_from_sender(kwargs)
        task_id = utils.retrieve_task_id_from_request(kwargs)
        reason = utils.retrieve_reason(kwargs)
        task_name = task.name if task is not None else None
        worker = _retrieve_worker_name(task=task) if task is not None else None
        _log_signal("task_retry", task_id, task_name, worker)

        if task is None or task_id is None or reason is None:
            return

        ctx = utils.retrieve_context(task, task_id)

        if ctx is None:
            return

        span, _, _ = ctx

        if not span.is_recording():
            return

        # Add retry reason metadata to span
        # Use `str(reason)` instead of `reason.message` in case we get
        # something that isn't an `Exception`
        span.set_attribute(_TASK_RETRY_REASON_KEY, str(reason))
        worker = _retrieve_worker_name(task=task)
        self._record_event_count(_EVENT_TYPES.task_retried, task.name, worker)

    def update_task_duration_time(self, task_id: str) -> None:
        """Update the duration time for a task by calculating the time since it was last started or updated."""
        cur_time = default_timer()
        task_duration_time_until_now = (
            cur_time - self.task_id_to_start_time[task_id]
            if task_id in self.task_id_to_start_time
            else cur_time
        )
        self.task_id_to_start_time[task_id] = task_duration_time_until_now

    def _record_histograms(
        self,
        task_id: Optional[str],
        metric_attributes: dict[str, str],
    ) -> None:
        """Record histogram metrics for a task by using its duration time and provided attributes."""
        if task_id is None:
            return

        task_duration = self.task_id_to_start_time.get(task_id)
        if task_duration is not None:
            self._metrics().task_runtime_seconds.record(
                task_duration,
                attributes=metric_attributes,
            )

    @staticmethod
    def create_task_metrics(meter: "Meter") -> CeleryTaskMetrics:
        """Create the metrics for tracking Celery task events and states."""
        return CeleryTaskMetrics(
            events_total=meter.create_counter(
                name=_TASK_METRIC_NAMES.events_total,
                unit="{event}",
                description=(
                    "Number of task and worker events recorded "
                    "by Celery instrumentation."
                ),
            ),
            task_runtime_seconds=meter.create_histogram(
                name=_TASK_METRIC_NAMES.task_runtime_seconds,
                unit="seconds",
                description="The time it took to run the task.",
            ),
            worker_currently_executing_tasks=meter.create_up_down_counter(
                name=_TASK_METRIC_NAMES.worker_currently_executing_tasks,
                unit="{task}",
                description="Number of tasks currently executing at this worker.",
            ),
        )


class CeleryWorkerInstrumentor(BaseInstrumentor):
    """An instrumentor for Celery worker lifecycle metrics.

    Tracks worker online/offline status via the ``worker_ready`` and
    ``worker_shutdown`` signals.  These signals fire in the **main worker
    process**, so this instrumentor must be initialized there — typically
    via the ``celeryd_after_setup`` signal (which fires before
    ``worker_ready``, giving the handler time to connect).

    Usage::

        from opentelemetry.instrumentation.celery import CeleryWorkerInstrumentor
        from celery.signals import celeryd_after_setup

        @celeryd_after_setup.connect(weak=False)
        def init_worker_metrics(sender, instance, conf, **kwargs):
            CeleryWorkerInstrumentor().instrument()
    """

    def __init__(self) -> None:
        super().__init__()
        self.metrics: Optional[CeleryWorkerMetrics] = None
        self.online_workers: set = set()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: object) -> None:
        """Connect worker lifecycle signal handlers and create worker metrics."""
        meter_provider = cast(
            Optional[metrics.MeterProvider], kwargs.get("meter_provider")
        )
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        self.online_workers = set()
        self.metrics = self._create_worker_metrics(meter)

        signals.worker_ready.connect(self._trace_worker_ready, weak=False)
        signals.worker_shutdown.connect(
            self._trace_worker_shutdown, weak=False
        )
        signals.task_received.connect(self._trace_task_received, weak=False)
        signals.task_revoked.connect(self._trace_task_revoked, weak=False)

    def _uninstrument(self, **kwargs: object) -> None:
        """Disconnect worker lifecycle signal handlers."""
        signals.worker_ready.disconnect(self._trace_worker_ready)
        signals.worker_shutdown.disconnect(self._trace_worker_shutdown)
        signals.task_received.disconnect(self._trace_task_received)
        signals.task_revoked.disconnect(self._trace_task_revoked)
        self.metrics = None
        self.online_workers = set()

    def _worker_metrics(self) -> CeleryWorkerMetrics:
        """Return the worker metrics, raising if not yet initialized."""
        if self.metrics is not None:
            return self.metrics
        raise RuntimeError("Worker metrics are not initialized")

    def _trace_worker_ready(self, *args: object, **kwargs: object) -> None:
        """Track a worker coming online."""
        worker = _retrieve_worker_name(sender=kwargs.get("sender"))
        _log_signal("worker_ready", None, None, worker)
        if worker is None or worker in self.online_workers:
            return

        self.online_workers.add(worker)
        self._worker_metrics().worker_online.add(
            1,
            attributes={"worker": worker},
        )
        _log_signal("worker_ready", None, None, worker)

    def _trace_worker_shutdown(self, *args: object, **kwargs: object) -> None:
        """Track a worker going offline."""
        worker = _retrieve_worker_name(sender=kwargs.get("sender"))
        _log_signal("worker_shutdown", None, None, worker)
        if worker is None or worker not in self.online_workers:
            return

        self.online_workers.remove(worker)
        self._worker_metrics().worker_online.add(
            -1,
            attributes={"worker": worker},
        )

    def _record_event_count(
        self,
        event_type: str,
        task_name: Optional[str] = None,
        worker: Optional[str] = None,
    ) -> None:
        """Record a Celery event by incrementing the events counter."""
        if task_name is None:
            return

        attributes: dict[str, str] = {
            "type": event_type,
            "task": task_name,
        }
        if worker is not None:
            attributes["worker"] = worker
        self._worker_metrics().events_total.add(
            1,
            attributes=attributes,
        )

    def _trace_task_received(
        self, *args: object, **kwargs: dict[str, Any]
    ) -> None:
        """Track a received task by recording its received time and incrementing the task received event counter.

        https://docs.celeryq.dev/en/main/userguide/signals.html#task-received
        """
        request = kwargs.get("request")
        task_id = getattr(request, "id", None)
        task_name = _retrieve_task_name(request=request)
        worker = _retrieve_worker_name(
            request=request, sender=kwargs.get("sender")
        )
        _log_signal(
            "task_received",
            task_id,
            task_name,
            worker,
        )
        if task_id is None or not isinstance(request, Request):
            return

        self._record_event_count(_EVENT_TYPES.task_received, task_name, worker)

    def _trace_task_revoked(self, *args: object, **kwargs: object) -> None:
        """Trace a task revoked event by untracking the task and incrementing the revoked event counter.

        https://docs.celeryq.dev/en/main/userguide/signals.html#task-revoked
        """
        request = kwargs.get("request")
        task_id = getattr(request, "id", None)
        task_name = _retrieve_task_name(request=request)
        worker = _retrieve_worker_name(
            request=request, sender=kwargs.get("sender")
        )
        _log_signal(
            "task_revoked",
            task_id,
            task_name,
            worker,
        )
        if task_id is None or request is None:
            return

        self._record_event_count(_EVENT_TYPES.task_revoked, task_name, worker)

    @staticmethod
    def _create_worker_metrics(meter: "Meter") -> CeleryWorkerMetrics:
        """Create the metrics for tracking Celery worker lifecycle."""
        return CeleryWorkerMetrics(
            events_total=meter.create_counter(
                name=_WORKER_METRIC_NAMES.events_total,
                unit="{event}",
                description=(
                    "Number of task and worker events recorded "
                    "by Celery instrumentation."
                ),
            ),
            worker_online=meter.create_up_down_counter(
                name=_WORKER_METRIC_NAMES.worker_online,
                unit="{worker}",
                description="Shows celery worker online status.",
            ),
        )
