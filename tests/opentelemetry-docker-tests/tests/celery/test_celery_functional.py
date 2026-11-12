# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import product
from socket import gethostname
from threading import Event
from typing import Any

import celery
from celery.exceptions import Retry
from kombu import Exchange, Queue
from pytest import mark

import opentelemetry.instrumentation.celery
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.celery import CeleryInstrumentor, utils
from opentelemetry.sdk import resources
from opentelemetry.sdk.trace import TracerProvider, export
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.semconv._incubating.attributes.exception_attributes import (
    EXCEPTION_MESSAGE,
    EXCEPTION_TYPE,
)
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
)
from opentelemetry.semconv.trace import MessagingDestinationKindValues, SpanAttributes
from opentelemetry.trace import StatusCode

# set a high timeout for async executions due to issues in CI
ASYNC_GET_TIMEOUT = 120


class MyException(Exception):
    pass


@mark.celery(
    task_queues=tuple(
        Queue(
            f"otel-{exchange_type}",
            exchange=Exchange(f"otel-{exchange_type}", type=exchange_type),
            routing_key=f"otel.{exchange_type}",
        )
        for exchange_type in ("direct", "topic")
    ),
)
def test_task_attributes(celery_app: celery.Celery, memory_exporter: InMemorySpanExporter) -> None:
    @celery_app.task
    def task(fail: bool) -> int:
        if fail:
            raise MyException("attribute test failure")
        return 42

    for exchange_type, fail in product(("direct", "topic"), (False, True)):
        _assert_task_attributes(task, memory_exporter, exchange_type, fail)


def _assert_task_attributes(
    task: celery.Task,
    memory_exporter: InMemorySpanExporter,
    exchange_type: str,
    fail: bool,
) -> None:
    exchange = Exchange(f"otel-{exchange_type}", type=exchange_type)
    routing_key = f"otel.{exchange_type}"
    queue = Queue(f"otel-{exchange_type}", exchange=exchange, routing_key=routing_key)
    memory_exporter.clear()

    # The result backend can be ready before task_postrun ends the run span.
    finished = Event()

    def task_finished(**kwargs: Any) -> None:
        finished.set()

    celery.signals.task_postrun.connect(task_finished, sender=task, weak=False)
    eta = datetime.now(timezone.utc) + timedelta(seconds=1)
    expires = eta + timedelta(minutes=5)
    try:
        result = task.apply_async(
            args=(fail,),
            queue=queue,
            exchange=exchange.name,
            routing_key=routing_key,
            correlation_id="otel-conversation",
            reply_to="otel-reply",
            origin="otel-publisher",
            retries=2,
            eta=eta,
            expires=expires,
            soft_time_limit=10,
            time_limit=20,
            priority=4,
            compression="gzip",
            # Celery also exposes custom message headers on task.request.
            headers={
                "countdown": 1,
                "exchange": exchange.name,
                "priority": 4,
                "queue": queue.name,
                "routing_key": routing_key,
                "serializer": "json",
            },
        )
        value = result.get(timeout=ASYNC_GET_TIMEOUT, propagate=False)
        if fail:
            assert isinstance(value, MyException)
        else:
            assert value == 42
        assert finished.wait(ASYNC_GET_TIMEOUT)
    finally:
        celery.signals.task_postrun.disconnect(task_finished, sender=task)

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 2
    publish_span = next(span for span in spans if span.attributes["celery.action"] == "apply_async")
    run_span = next(span for span in spans if span.attributes["celery.action"] == "run")
    expected_publish = {
        "celery.action": "apply_async",
        "celery.task_name": task.name,
        MESSAGING_MESSAGE_ID: result.id,
        "celery.exchange": exchange.name,
        SpanAttributes.MESSAGING_DESTINATION: routing_key,
        SpanAttributes.MESSAGING_DESTINATION_KIND: (
            MessagingDestinationKindValues.QUEUE.value
            if exchange_type == "direct"
            else MessagingDestinationKindValues.TOPIC.value
        ),
    }
    delivery_info = {"exchange": exchange.name, "routing_key": routing_key, "priority": 4, "redelivered": False}
    expected_run = {
        "celery.compression": "application/x-gzip",
        "celery.countdown": 1,
        "celery.exchange": exchange.name,
        "celery.priority": 4,
        "celery.queue": queue.name,
        "celery.serializer": "json",
        "celery.action": "run",
        "celery.task_name": task.name,
        MESSAGING_MESSAGE_ID: result.id,
        SpanAttributes.MESSAGING_CONVERSATION_ID: "otel-conversation",
        SpanAttributes.MESSAGING_DESTINATION: routing_key,
        "celery.delivery_info": str(delivery_info),
        "celery.eta": eta.isoformat(),
        "celery.expires": expires.isoformat(),
        "celery.hostname": gethostname(),
        "celery.origin": "otel-publisher",
        "celery.reply_to": "otel-reply",
        "celery.retries": 2,
        "celery.timelimit": (20, 10),
        "celery.state": "FAILURE" if fail else "SUCCESS",
    }
    # Keep the explicit expectations exhaustive as request metadata evolves.
    assert set(utils.CELERY_REQUEST_ATTRIBUTES) == {
        "compression",
        "countdown",
        "exchange",
        "priority",
        "queue",
        "routing_key",
        "serializer",
        "id",
        "correlation_id",
        "delivery_info",
        "eta",
        "expires",
        "hostname",
        "origin",
        "reply_to",
        "retries",
        "timelimit",
    }
    for span, expected in ((publish_span, expected_publish), (run_span, expected_run)):
        assert dict(span.attributes) == expected
        for key, value in expected.items():
            assert type(span.attributes[key]) is type(value)
            if isinstance(value, tuple):
                assert all(type(item) is int for item in span.attributes[key])
    assert run_span.status.status_code == (StatusCode.ERROR if fail else StatusCode.UNSET)


@mark.skip(reason="inconsistent test results")
def test_instrumentation_info(celery_app, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    result = fn_task.apply_async()
    assert result.get(timeout=ASYNC_GET_TIMEOUT) == 42

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 2

    async_span, run_span = spans

    assert run_span.parent == async_span.context
    assert run_span.parent.span_id == async_span.context.span_id
    assert run_span.context.trace_id == async_span.context.trace_id

    assert async_span.instrumentation_info.name == f"apply_async/{opentelemetry.instrumentation.celery.__name__}"
    assert async_span.instrumentation_info.version == f"apply_async/{opentelemetry.instrumentation.celery.__version__}"
    assert run_span.instrumentation_info.name == f"run/{opentelemetry.instrumentation.celery.__name__}"
    assert run_span.instrumentation_info.version == f"run/{opentelemetry.instrumentation.celery.__version__}"


def test_fn_task_run(celery_app, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    t = fn_task.run()
    assert t == 42

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 0


def test_fn_task_call(celery_app, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    t = fn_task()
    assert t == 42

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 0


def test_fn_task_apply(celery_app, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    t = fn_task.apply()
    assert t.successful() is True
    assert t.result == 42

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is True
    assert span.name == "run/test_celery_functional.fn_task"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == t.task_id
    assert span.attributes.get("celery.task_name") == "test_celery_functional.fn_task"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "SUCCESS"


def test_fn_task_apply_bind(celery_app, memory_exporter):
    @celery_app.task(bind=True)
    def fn_task(self):
        return self

    t = fn_task.apply()
    assert t.successful() is True
    assert "fn_task" in t.result.name

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is True
    assert span.name == "run/test_celery_functional.fn_task"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == t.task_id
    assert span.attributes.get("celery.task_name") == "test_celery_functional.fn_task"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "SUCCESS"


@mark.skip(reason="inconsistent test results")
def test_fn_task_apply_async(celery_app, memory_exporter):
    @celery_app.task
    def fn_task_parameters(user, force_logout=False):
        return (user, force_logout)

    result = fn_task_parameters.apply_async(args=["user"], kwargs={"force_logout": True})
    assert result.get(timeout=ASYNC_GET_TIMEOUT) == ["user", True]

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 2

    async_span, run_span = spans

    assert run_span.context.trace_id != async_span.context.trace_id

    assert async_span.status.is_ok is True
    assert async_span.name == "apply_async/test_celery_functional.fn_task_parameters"
    assert async_span.attributes.get("celery.action") == "apply_async"
    assert async_span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id
    assert async_span.attributes.get("celery.task_name") == "test_celery_functional.fn_task_parameters"

    assert run_span.status.is_ok is True
    assert run_span.name == "test_celery_functional.fn_task_parameters"
    assert run_span.attributes.get("celery.action") == "run"
    assert run_span.attributes.get("celery.state") == "SUCCESS"
    assert run_span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id
    assert run_span.attributes.get("celery.task_name") == "test_celery_functional.fn_task_parameters"


@mark.skip(reason="inconsistent test results")
def test_concurrent_delays(celery_app, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    results = [fn_task.delay() for _ in range(100)]

    for result in results:
        assert result.get(timeout=ASYNC_GET_TIMEOUT) == 42

    spans = memory_exporter.get_finished_spans()

    assert len(spans) == 200


@mark.skip(reason="inconsistent test results")
def test_fn_task_delay(celery_app, memory_exporter):
    @celery_app.task
    def fn_task_parameters(user, force_logout=False):
        return (user, force_logout)

    result = fn_task_parameters.delay("user", force_logout=True)
    assert result.get(timeout=ASYNC_GET_TIMEOUT) == ["user", True]

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 2

    async_span, run_span = spans

    assert run_span.context.trace_id != async_span.context.trace_id

    assert async_span.status.is_ok is True
    assert async_span.name == "apply_async/test_celery_functional.fn_task_parameters"
    assert async_span.attributes.get("celery.action") == "apply_async"
    assert async_span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id
    assert async_span.attributes.get("celery.task_name") == "test_celery_functional.fn_task_parameters"

    assert run_span.status.is_ok is True
    assert run_span.name == "run/test_celery_functional.fn_task_parameters"
    assert run_span.attributes.get("celery.action") == "run"
    assert run_span.attributes.get("celery.state") == "SUCCESS"
    assert run_span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id
    assert run_span.attributes.get("celery.task_name") == "test_celery_functional.fn_task_parameters"
    assert len(run_span.events) == 0


def test_fn_exception(celery_app, memory_exporter):
    @celery_app.task
    def fn_exception():
        raise Exception("Task class is failing")

    result = fn_exception.apply()

    assert result.failed() is True
    assert "Task class is failing" in result.traceback

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is False
    assert span.name == "run/test_celery_functional.fn_exception"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "FAILURE"
    assert span.attributes.get("celery.task_name") == "test_celery_functional.fn_exception"
    assert span.status.status_code == StatusCode.ERROR
    assert len(span.events) == 1
    event = span.events[0]
    assert event.name == "exception"
    assert event.attributes[EXCEPTION_TYPE] == "Exception"
    assert EXCEPTION_MESSAGE in event.attributes
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id
    assert "Task class is failing" in span.status.description


def test_fn_exception_expected(celery_app, memory_exporter):
    @celery_app.task(throws=(MyException,))
    def fn_exception():
        raise MyException("Task class is failing")

    result = fn_exception.apply()

    assert result.failed() is True
    assert "Task class is failing" in result.traceback

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is False
    assert span.status.status_code == StatusCode.ERROR
    assert span.name == "run/test_celery_functional.fn_exception"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "FAILURE"
    assert span.attributes.get("celery.task_name") == "test_celery_functional.fn_exception"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id


def test_fn_retry_exception(celery_app, memory_exporter):
    @celery_app.task
    def fn_exception():
        raise Retry("Task class is being retried")

    result = fn_exception.apply()

    assert result.failed() is False
    assert "Task class is being retried" in result.traceback

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is True
    assert span.status.status_code == StatusCode.UNSET
    assert span.name == "run/test_celery_functional.fn_exception"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "RETRY"
    assert span.attributes.get("celery.task_name") == "test_celery_functional.fn_exception"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id


def test_class_task(celery_app, memory_exporter):
    class BaseTask(celery_app.Task):
        def run(self):
            return 42

    task = BaseTask()
    # register the Task class if it's available (required in Celery 4.0+)
    register_task = getattr(celery_app, "register_task", None)
    if register_task is not None:
        register_task(task)

    result = task.apply()

    assert result.successful() is True
    assert result.result == 42

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is True
    assert span.name == "run/test_celery_functional.BaseTask"
    assert span.attributes.get("celery.task_name") == "test_celery_functional.BaseTask"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "SUCCESS"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id


def test_class_task_exception(celery_app, memory_exporter):
    class BaseTask(celery_app.Task):
        def run(self):
            raise Exception("Task class is failing")

    task = BaseTask()
    # register the Task class if it's available (required in Celery 4.0+)
    register_task = getattr(celery_app, "register_task", None)
    if register_task is not None:
        register_task(task)

    result = task.apply()

    assert result.failed() is True
    assert "Task class is failing" in result.traceback

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is False
    assert span.name == "run/test_celery_functional.BaseTask"
    assert span.attributes.get("celery.task_name") == "test_celery_functional.BaseTask"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "FAILURE"
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id
    assert "Task class is failing" in span.status.description


def test_class_task_exception_expected(celery_app, memory_exporter):
    class BaseTask(celery_app.Task):
        throws = (MyException,)

        def run(self):
            raise MyException("Task class is failing")

    task = BaseTask()
    # register the Task class if it's available (required in Celery 4.0+)
    register_task = getattr(celery_app, "register_task", None)
    if register_task is not None:
        register_task(task)

    result = task.apply()

    assert result.failed() is True
    assert "Task class is failing" in result.traceback

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is False
    assert span.status.status_code == StatusCode.ERROR
    assert span.name == "run/test_celery_functional.BaseTask"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "FAILURE"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id


def test_shared_task(celery_app, memory_exporter):
    """Ensure Django Shared Task are supported"""

    @celery.shared_task
    def add(x, y):
        return x + y

    result = add.apply([2, 2])
    assert result.result == 4

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.is_ok is True
    assert span.name == "run/test_celery_functional.add"
    assert span.attributes.get("celery.task_name") == "test_celery_functional.add"
    assert span.attributes.get("celery.action") == "run"
    assert span.attributes.get("celery.state") == "SUCCESS"
    assert span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id


@mark.skip(reason="inconsistent test results")
def test_apply_async_previous_style_tasks(celery_app, celery_worker, memory_exporter):
    """Ensures apply_async is properly patched if Celery 1.0 style tasks are
    used even in newer versions. This should extend support to previous versions
    of Celery."""

    class CelerySuperClass(celery.task.Task):
        abstract = True

        @classmethod
        def apply_async(cls, args=None, kwargs=None, **kwargs_):
            return super().apply_async(args=args, kwargs=kwargs, **kwargs_)

        def run(self, *args, **kwargs):
            if "stop" in kwargs:
                # avoid call loop
                return
            CelerySubClass.apply_async(args=[], kwargs={"stop": True}).get(timeout=ASYNC_GET_TIMEOUT)

    class CelerySubClass(CelerySuperClass):
        pass

    celery_worker.reload()

    task = CelerySubClass()
    result = task.apply()

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 3

    async_span, async_run_span, run_span = spans

    assert run_span.status.is_ok is True
    assert run_span.name == "run/test_celery_functional.CelerySubClass"
    assert run_span.attributes.get("celery.task_name") == "test_celery_functional.CelerySubClass"
    assert run_span.attributes.get("celery.action") == "run"
    assert run_span.attributes.get("celery.state") == "SUCCESS"
    assert run_span.attributes.get(MESSAGING_MESSAGE_ID) == result.task_id

    assert async_run_span.status.is_ok is True
    assert async_run_span.name == "run/test_celery_functional.CelerySubClass"
    assert async_run_span.attributes.get("celery.task_name") == "test_celery_functional.CelerySubClass"
    assert async_run_span.attributes.get("celery.action") == "run"
    assert async_run_span.attributes.get("celery.state") == "SUCCESS"
    assert async_run_span.attributes.get(MESSAGING_MESSAGE_ID) != result.task_id

    assert async_span.status.is_ok is True
    assert async_span.name == "apply_async/test_celery_functional.CelerySubClass"
    assert async_span.attributes.get("celery.task_name") == "test_celery_functional.CelerySubClass"
    assert async_span.attributes.get("celery.action") == "apply_async"
    assert async_span.attributes.get(MESSAGING_MESSAGE_ID) != result.task_id
    assert async_span.attributes.get(MESSAGING_MESSAGE_ID) == async_run_span.attributes.get(MESSAGING_MESSAGE_ID)


def test_custom_tracer_provider(celery_app, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    resource = resources.Resource.create({})
    tracer_provider = TracerProvider(resource=resource)
    span_processor = export.SimpleSpanProcessor(memory_exporter)
    tracer_provider.add_span_processor(span_processor)

    trace_api.set_tracer_provider(tracer_provider)

    CeleryInstrumentor().uninstrument()
    CeleryInstrumentor().instrument(tracer_provider=tracer_provider)

    fn_task.apply()

    spans_list = memory_exporter.get_finished_spans()
    assert len(spans_list) == 1

    span = spans_list[0]
    assert span.resource == resource


def test_use_span_links(celery_app, tracer_provider, memory_exporter):
    @celery_app.task
    def fn_task():
        return 42

    CeleryInstrumentor().uninstrument()
    CeleryInstrumentor().instrument(tracer_provider=tracer_provider, use_span_links=True)

    result = fn_task.apply_async()
    assert result.get(timeout=ASYNC_GET_TIMEOUT) == 42

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 2

    run_span = next(s for s in spans if s.attributes.get("celery.action") == "run")
    async_span = next(s for s in spans if s.attributes.get("celery.action") == "apply_async")

    # The run span should not be a child of the async span when using links.
    assert run_span.parent is None
    assert run_span.context.trace_id != async_span.context.trace_id

    assert len(run_span.links) == 1
    link = run_span.links[0]
    assert link.context.span_id == async_span.context.span_id
    assert link.context.trace_id == async_span.context.trace_id
