# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import threading
import time

from celery.signals import after_task_publish, before_task_publish, task_postrun, task_prerun
from kombu import Exchange, Queue
from wrapt import wrap_function_wrapper

from opentelemetry import baggage, context
from opentelemetry.instrumentation.celery import CeleryInstrumentor, utils
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes.messaging_attributes import MESSAGING_MESSAGE_ID
from opentelemetry.semconv.attributes.exception_attributes import (
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.samplertestutil import CapturingSampler
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode

from .celery_test_tasks import (
    CustomError,
    app,
    task_add,
    task_raises,
    task_returns_baggage,
)


class TestCeleryPublishSignal(TestBase):
    def tearDown(self):
        super().tearDown()
        CeleryInstrumentor().uninstrument()

    def test_before_task_publish_with_kombu_exchange(self):
        CeleryInstrumentor().instrument()

        headers = {"id": "task-id"}
        signal_kwargs = {
            "sender": task_add.name,
            "headers": headers,
            "body": None,
            "exchange": Exchange("celery_delayed_27", type="topic"),
            "routing_key": "celery",
        }

        before_task_publish.send(**signal_kwargs)
        after_task_publish.send(**signal_kwargs)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes["celery.exchange"], "celery_delayed_27")


class TestCelerySampling(TestBase):
    def tearDown(self) -> None:
        CeleryInstrumentor().uninstrument()
        super().tearDown()

    def _instrument_with_sampler(self, sampler: CapturingSampler, use_span_links: bool = False) -> None:
        self.tracer_provider, self.memory_exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(self.tracer_provider.shutdown)
        instrumentor = CeleryInstrumentor()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        instrumentor.instrument(tracer_provider=self.tracer_provider, use_span_links=use_span_links)

    def test_publish_attributes_passed_to_sampler(self) -> None:
        sampler = CapturingSampler()
        self._instrument_with_sampler(sampler)
        signal_kwargs = {
            "sender": task_add.name,
            "headers": {"id": "task-id"},
            "body": None,
            "exchange": Exchange("celery", type="direct"),
            "routing_key": "celery",
            "declare": [Queue("celery", exchange=Exchange("celery", type="direct"))],
            "properties": {"priority": 4},
        }

        before_task_publish.send(**signal_kwargs)
        after_task_publish.send(**signal_kwargs)

        expected = {
            "celery.action": "apply_async",
            MESSAGING_MESSAGE_ID: "task-id",
            "celery.task_name": task_add.name,
            "celery.exchange": "celery",
            SpanAttributes.MESSAGING_DESTINATION: "celery",
            SpanAttributes.MESSAGING_DESTINATION_KIND: "queue",
        }
        self.assertEqual(sampler.kind, SpanKind.PRODUCER)
        self.assertEqual(sampler.attributes, expected)
        for key, value in expected.items():
            self.assertIs(type(sampler.attributes[key]), type(value))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes, expected)

    def test_prerun_attributes_passed_to_sampler(self) -> None:
        for use_span_links in (False, True):
            with self.subTest(use_span_links=use_span_links):
                sampler = CapturingSampler()
                self._instrument_with_sampler(sampler, use_span_links=use_span_links)
                task_add.push_request(
                    id="task-id",
                    correlation_id="correlation-id",
                    hostname="worker",
                    origin="publisher",
                    delivery_info={"routing_key": "celery"},
                    retries=2,
                    timelimit=(None, 10),
                    traceparent="00-03afa25236b8cd948fa853d67038ac79-405ff022e8247c46-01",
                )
                self.addCleanup(task_add.pop_request)
                signal_kwargs = {"sender": task_add, "task": task_add, "task_id": "task-id"}

                task_prerun.send(**signal_kwargs)
                task_postrun.send(**signal_kwargs, state="SUCCESS")

                expected = {
                    "celery.action": "run",
                    "celery.task_name": task_add.name,
                    MESSAGING_MESSAGE_ID: "task-id",
                    SpanAttributes.MESSAGING_CONVERSATION_ID: "correlation-id",
                    "celery.hostname": "worker",
                    "celery.origin": "publisher",
                    "celery.delivery_info": str({"routing_key": "celery"}),
                    SpanAttributes.MESSAGING_DESTINATION: "celery",
                    "celery.retries": 2,
                    "celery.timelimit": ["", "10"],
                }
                self.assertEqual(sampler.kind, SpanKind.CONSUMER)
                self.assertEqual(sampler.attributes, expected)
                for key, value in expected.items():
                    self.assertIs(type(sampler.attributes[key]), type(value))
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                expected["celery.timelimit"] = ("", "10")
                expected["celery.state"] = "SUCCESS"
                self.assertEqual(spans[0].attributes, expected)
                if use_span_links:
                    self.assertIsNone(spans[0].parent)
                    self.assertEqual(len(spans[0].links), 1)
                else:
                    self.assertEqual(spans[0].parent.span_id, 0x405FF022E8247C46)

    def test_postrun_state(self) -> None:
        self._instrument_with_sampler(CapturingSampler())
        for state_kwargs in ({}, {"state": None}, {"state": ""}, {"state": "SUCCESS"}, {"state": "FAILURE"}):
            with self.subTest(state_kwargs=state_kwargs):
                task_add.push_request(id="task-id", hostname="worker")
                try:
                    signal_kwargs = {"sender": task_add, "task": task_add, "task_id": "task-id"}
                    task_prerun.send(**signal_kwargs)
                    task_postrun.send(**signal_kwargs, **state_kwargs)
                finally:
                    task_add.pop_request()

                span = self.memory_exporter.get_finished_spans()[-1]
                state = state_kwargs.get("state")
                if state:
                    self.assertEqual(span.attributes["celery.state"], state)
                    self.assertIs(type(span.attributes["celery.state"]), str)
                else:
                    self.assertNotIn("celery.state", span.attributes)

    def test_attributes_control_sampling_apply_async(self) -> None:
        for routing_key, expected_count in (("sample", 1), ("drop", 0)):
            with self.subTest(routing_key=routing_key):
                sampler = CapturingSampler(required_attributes={SpanAttributes.MESSAGING_DESTINATION: "sample"})
                self._instrument_with_sampler(sampler)
                signal_kwargs = {
                    "sender": task_add.name,
                    "headers": {"id": "task-id"},
                    "body": None,
                    "routing_key": routing_key,
                }
                before_task_publish.send(**signal_kwargs)
                after_task_publish.send(**signal_kwargs)
                self.assertEqual(len(self.memory_exporter.get_finished_spans()), expected_count)
                self.assertIsNone(utils.retrieve_context(task_add, "task-id", is_publish=True))

    def test_attributes_control_sampling_run(self) -> None:
        for routing_key, expected_count in (("sample", 1), ("drop", 0)):
            with self.subTest(routing_key=routing_key):
                sampler = CapturingSampler(required_attributes={SpanAttributes.MESSAGING_DESTINATION: "sample"})
                self._instrument_with_sampler(sampler)
                task_add.push_request(id="task-id", hostname="worker", delivery_info={"routing_key": routing_key})
                self.addCleanup(task_add.pop_request)
                signal_kwargs = {"sender": task_add, "task": task_add, "task_id": "task-id"}
                task_prerun.send(**signal_kwargs)
                task_postrun.send(**signal_kwargs, state="SUCCESS")
                self.assertEqual(len(self.memory_exporter.get_finished_spans()), expected_count)
                self.assertIsNone(utils.retrieve_context(task_add, "task-id", is_publish=False))


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

        result = task_add.delay(1, 2)

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

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

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

        self.assertTrue(result.ready())
        self.assertEqual(result.result, 3)
        self.assertEqual(instrumentor.task_id_to_start_time, {})

    def test_task_raises(self):
        CeleryInstrumentor().instrument()

        result = task_raises.delay()

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

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

        CeleryInstrumentor().instrument()

        result = task_add.delay(1, 2)

        timeout = time.time() + 60 * 1  # 1 minutes from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        # TODO: assert we don't have "TypeError: expected an instance of Token, got None" in logs
        self.assertTrue(result)

        unwrap(utils, "retrieve_context")

    def test_task_use_span_links(self):
        CeleryInstrumentor().instrument(use_span_links=True)

        result = task_add.delay(1, 2)

        timeout = time.time() + 60 * 1  # 1 minute from now
        while not result.ready():
            if time.time() > timeout:
                break
            time.sleep(0.05)

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

        res = app.signature("tests.test_tasks.hidden_task", (2,)).apply_async()
        while not res.ready():
            time.sleep(0.05)
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
