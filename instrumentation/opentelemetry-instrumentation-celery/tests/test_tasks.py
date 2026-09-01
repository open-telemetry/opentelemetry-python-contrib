# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import threading
import time

from wrapt import wrap_function_wrapper

from opentelemetry import baggage, context
from opentelemetry.instrumentation.celery import CeleryInstrumentor, utils
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.attributes.exception_attributes import (
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode

from .celery_test_tasks import (
    CustomError,
    app,
    task_add,
    task_raises,
    task_returns_baggage,
)


def wait_for(predicate, message, timeout_s=60):
    """Poll ``predicate`` until it is true, failing the test if it never is."""
    deadline = time.time() + timeout_s
    while not predicate():
        if time.time() > deadline:
            raise AssertionError(f"timed out after {timeout_s}s waiting for {message}")
        time.sleep(0.05)


def wait_for_spans(exporter, span_count, timeout_s=60):
    """Wait until ``span_count`` spans have been exported.

    Celery stores the task result before it dispatches ``task_postrun``, and the
    instrumentation ends the run span from ``task_postrun``. So an ``AsyncResult``
    can be ready while the run span has not been ended and exported yet, and
    waiting on ``result.ready()`` alone makes the span assertions racy.
    """
    wait_for(
        lambda: len(exporter.get_finished_spans()) >= span_count,
        f"{span_count} spans to be exported",
        timeout_s,
    )


class TestCeleryInstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        self._worker = app.Worker(app=app, pool="solo", concurrency=1)
        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        super().tearDown()
        CeleryInstrumentor().uninstrument()
        self._worker.stop()
        self._thread.join()
        CeleryInstrumentor().uninstrument()

    def test_task(self):
        CeleryInstrumentor().instrument()

        task_add.delay(1, 2)

        wait_for_spans(self.memory_exporter, 2)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "run/tests.celery_test_tasks.task_add")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "celery.action": "run",
                "celery.state": "SUCCESS",
                SpanAttributes.MESSAGING_DESTINATION: "celery",
                "celery.task_name": "tests.celery_test_tasks.task_add",
            },
        )

        self.assertEqual(consumer.status.status_code, StatusCode.UNSET)

        self.assertEqual(0, len(consumer.events))

        self.assertEqual(producer.name, "apply_async/tests.celery_test_tasks.task_add")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "celery.action": "apply_async",
                "celery.task_name": "tests.celery_test_tasks.task_add",
                SpanAttributes.MESSAGING_DESTINATION_KIND: "queue",
                SpanAttributes.MESSAGING_DESTINATION: "celery",
            },
        )

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)

    def test_task_clears_start_time_cache(self):
        """Test that the `task_id_to_start_time` cache is cleared after a task finishes,
        to prevent memory leaks."""
        instrumentor = CeleryInstrumentor()
        instrumentor.instrument()

        result = task_add.delay(1, 2)

        wait_for_spans(self.memory_exporter, 2)
        # the cache is cleared a few statements after the run span is ended, in
        # the same task_postrun receiver, so it needs its own wait
        wait_for(
            lambda: not instrumentor.task_id_to_start_time,
            "the task start time cache to be cleared",
        )

        self.assertTrue(result.ready())
        self.assertEqual(result.result, 3)
        self.assertEqual(instrumentor.task_id_to_start_time, {})

    def test_task_raises(self):
        CeleryInstrumentor().instrument()

        task_raises.delay()

        wait_for_spans(self.memory_exporter, 2)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "run/tests.celery_test_tasks.task_raises")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "celery.action": "run",
                "celery.state": "FAILURE",
                SpanAttributes.MESSAGING_DESTINATION: "celery",
                "celery.task_name": "tests.celery_test_tasks.task_raises",
            },
        )

        self.assertEqual(consumer.status.status_code, StatusCode.ERROR)

        self.assertEqual(1, len(consumer.events))
        event = consumer.events[0]

        self.assertIn(EXCEPTION_STACKTRACE, event.attributes)

        self.assertEqual(
            f"{CustomError.__module__}.{CustomError.__qualname__}",
            event.attributes[EXCEPTION_TYPE],
        )

        self.assertEqual(
            event.attributes[EXCEPTION_MESSAGE],
            "The task failed!",
        )

        self.assertEqual(producer.name, "apply_async/tests.celery_test_tasks.task_raises")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "celery.action": "apply_async",
                "celery.task_name": "tests.celery_test_tasks.task_raises",
                SpanAttributes.MESSAGING_DESTINATION_KIND: "queue",
                SpanAttributes.MESSAGING_DESTINATION: "celery",
            },
        )

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)

    def test_uninstrument(self):
        CeleryInstrumentor().instrument()
        CeleryInstrumentor().uninstrument()

        result = task_add.delay(1, 2)

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_baggage(self):
        CeleryInstrumentor().instrument()

        ctx = baggage.set_baggage("key", "value")
        context.attach(ctx)

        task = task_returns_baggage.delay()

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not task.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

        self.assertEqual(task.result, {"key": "value"})

    def test_task_not_instrumented_does_not_raise(self):
        def _retrieve_context_wrapper_none_token(wrapped, instance, args, kwargs):
            ctx = wrapped(*args, **kwargs)
            if ctx is None:
                return ctx
            span, activation, _ = ctx
            return span, activation, None

        wrap_function_wrapper(
            utils,
            "retrieve_context",
            _retrieve_context_wrapper_none_token,
        )
        # Unconditional: an assertion or a wait_for_spans timeout below would
        # otherwise skip the cleanup and leave retrieve_context patched for the
        # rest of the process, since tearDown only uninstruments and never
        # unwraps this module-level patch.
        self.addCleanup(unwrap, utils, "retrieve_context")

        CeleryInstrumentor().instrument()

        result = task_add.delay(1, 2)

        wait_for_spans(self.memory_exporter, 2)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        # TODO: assert we don't have "TypeError: expected an instance of Token, got None" in logs
        self.assertTrue(result)

    def test_task_use_span_links(self):
        CeleryInstrumentor().instrument(use_span_links=True)

        task_add.delay(1, 2)

        wait_for_spans(self.memory_exporter, 2)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "run/tests.celery_test_tasks.task_add")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "celery.action": "run",
                "celery.state": "SUCCESS",
                SpanAttributes.MESSAGING_DESTINATION: "celery",
                "celery.task_name": "tests.celery_test_tasks.task_add",
            },
        )

        self.assertEqual(consumer.status.status_code, StatusCode.UNSET)
        self.assertEqual(0, len(consumer.events))

        self.assertEqual(producer.name, "apply_async/tests.celery_test_tasks.task_add")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "celery.action": "apply_async",
                "celery.task_name": "tests.celery_test_tasks.task_add",
                SpanAttributes.MESSAGING_DESTINATION_KIND: "queue",
                SpanAttributes.MESSAGING_DESTINATION: "celery",
            },
        )

        # Verify that consumer span is not a child of producer span when using links
        self.assertIsNone(consumer.parent)
        self.assertNotEqual(consumer.context.trace_id, producer.context.trace_id)

        # Verify that consumer span has a link to the producer span
        self.assertEqual(len(consumer.links), 1)
        link = consumer.links[0]
        self.assertEqual(link.context.span_id, producer.context.span_id)
        self.assertEqual(link.context.trace_id, producer.context.trace_id)


class TestCelerySignatureTask(TestBase):
    def setUp(self):
        super().setUp()

        def start_app(*args, **kwargs):
            # Add an additional task that will not be registered with parent thread
            @app.task
            def hidden_task(num_a):
                return num_a * 2

            self._worker = app.Worker(app=app, pool="solo", concurrency=1)
            return self._worker.start(*args, **kwargs)

        self._thread = threading.Thread(target=start_app)
        self._worker = app.Worker(app=app, pool="solo", concurrency=1)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        super().tearDown()
        self._worker.stop()
        self._thread.join()
        CeleryInstrumentor().uninstrument()

    def test_hidden_task(self):
        # no-op since already instrumented
        CeleryInstrumentor().instrument()

        app.signature("tests.test_tasks.hidden_task", (2,)).apply_async()
        wait_for_spans(self.memory_exporter, 2)
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "run/tests.test_tasks.hidden_task")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)

        self.assertEqual(producer.name, "apply_async/tests.test_tasks.hidden_task")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)
