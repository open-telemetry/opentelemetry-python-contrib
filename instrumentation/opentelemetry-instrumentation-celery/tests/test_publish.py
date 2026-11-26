# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from unittest import mock

from celery.signals import before_task_publish
from kombu import Producer
from kombu.exceptions import SerializerNotInstalled

from opentelemetry import trace
from opentelemetry.instrumentation.celery import CeleryInstrumentor, utils
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF
from opentelemetry.semconv._incubating.attributes.messaging_attributes import MESSAGING_MESSAGE_ID
from opentelemetry.semconv.attributes.exception_attributes import EXCEPTION_MESSAGE, EXCEPTION_TYPE
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode

from .celery_test_tasks import app, task_add


class TestCeleryPublishCleanup(TestBase):
    def setUp(self) -> None:
        super().setUp()
        CeleryInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self) -> None:
        CeleryInstrumentor().uninstrument()
        super().tearDown()

    def _assert_failed_publish(
        self, publish: Callable[[], object], task_name: str, exception_type: type[Exception]
    ) -> Exception:
        self.memory_exporter.clear()
        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("parent") as parent:
            with self.assertRaises(exception_type) as caught:
                publish()
            self.assertIs(trace.get_current_span(), parent)
            with tracer.start_as_current_span("after"):
                pass

        spans = self.memory_exporter.get_finished_spans()
        producer, after, finished_parent = spans
        self.assertEqual(producer.name, f"apply_async/{task_name}")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertEqual(producer.parent.span_id, parent.get_span_context().span_id)
        self.assertEqual(producer.status.status_code, StatusCode.ERROR)
        self.assertIs(type(producer.attributes[MESSAGING_MESSAGE_ID]), str)
        self.assertEqual(producer.attributes["celery.action"], "apply_async")
        self.assertIs(type(producer.attributes["celery.action"]), str)
        self.assertEqual(producer.attributes["celery.task_name"], task_name)
        self.assertIs(type(producer.attributes["celery.task_name"]), str)
        if task_name == task_add.name:
            self.assertIsNone(
                utils.retrieve_context(task_add, producer.attributes[MESSAGING_MESSAGE_ID], is_publish=True)
            )
        (exception,) = producer.events
        self.assertEqual(exception.name, "exception")
        self.assertEqual(exception.attributes[EXCEPTION_MESSAGE], str(caught.exception))
        qualified_type = exception_type.__qualname__
        if exception_type.__module__ != "builtins":
            qualified_type = f"{exception_type.__module__}.{qualified_type}"
        self.assertEqual(exception.attributes[EXCEPTION_TYPE], qualified_type)
        self.assertEqual(after.name, "after")
        self.assertEqual(after.parent.span_id, parent.get_span_context().span_id)
        self.assertEqual(finished_parent.context, parent.get_span_context())
        self.memory_exporter.clear()
        return caught.exception

    def test_serialization_failure_restores_context(self) -> None:
        for protocol in (1, 2):
            for task_name in (task_add.name, "remote.unregistered"):
                with self.subTest(protocol=protocol, task_name=task_name):
                    with mock.patch.object(app.amqp, "create_task_message", app.amqp.task_protocols[protocol]):
                        self._assert_failed_publish(
                            lambda task_name=task_name: app.send_task(
                                task_name, args=(1, 2), serializer="unavailable-serializer"
                            ),
                            task_name,
                            SerializerNotInstalled,
                        )

    def test_apply_async_failure_restores_context(self) -> None:
        self._assert_failed_publish(
            lambda: task_add.apply_async(args=(1, 2), serializer="unavailable-serializer"),
            task_add.name,
            SerializerNotInstalled,
        )

    def test_publish_failure_preserves_exception(self) -> None:
        for task_name in (task_add.name, "remote.unregistered"):
            with self.subTest(task_name=task_name):
                failure = RuntimeError("publication failed")
                with mock.patch("kombu.messaging.Producer.publish", side_effect=failure):
                    caught = self._assert_failed_publish(
                        lambda task_name=task_name: app.send_task(task_name, args=(1, 2)),
                        task_name,
                        RuntimeError,
                    )
                self.assertIs(caught, failure)

    def test_unregistered_task_span_is_active_during_publication(self) -> None:
        publish = Producer.publish
        active_spans = []

        def capture_span(producer: Producer, *args: object, **kwargs: object) -> object:
            span = trace.get_current_span()
            self.assertTrue(span.is_recording())
            active_spans.append(span)
            return publish(producer, *args, **kwargs)

        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("parent") as parent:
            with mock.patch.object(Producer, "publish", capture_span):
                app.send_task("remote.unregistered", args=(1, 2), queue="publish-cleanup", ignore_result=True)
            self.assertIs(trace.get_current_span(), parent)

        self.assertEqual(len(active_spans), 1)
        producer = active_spans[0]
        finished_producer, finished_parent = self.memory_exporter.get_finished_spans()
        self.assertEqual(finished_producer.context, producer.get_span_context())
        self.assertEqual(finished_producer.name, "apply_async/remote.unregistered")
        self.assertEqual(finished_producer.parent.span_id, finished_parent.context.span_id)
        self.assertEqual(finished_producer.status.status_code, StatusCode.UNSET)

    def test_next_publish_after_failure_uses_original_parent(self) -> None:
        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("parent") as parent:
            with self.assertRaises(SerializerNotInstalled):
                task_add.apply_async(args=(1, 2), serializer="unavailable-serializer")
            app.send_task(task_add.name, args=(1, 2), queue="publish-cleanup", ignore_result=True)
            self.assertIs(trace.get_current_span(), parent)

        failed, following, finished_parent = self.memory_exporter.get_finished_spans()
        self.assertEqual(failed.status.status_code, StatusCode.ERROR)
        self.assertEqual(following.status.status_code, StatusCode.UNSET)
        self.assertEqual(following.parent.span_id, finished_parent.context.span_id)
        self.assertEqual(following.context.trace_id, finished_parent.context.trace_id)

    def test_nested_publish_failure_restores_outer_producer(self) -> None:
        observed_contexts = []

        def publish_nested(sender: str, **_kwargs: object) -> None:
            if sender != task_add.name:
                return
            outer = trace.get_current_span()
            try:
                app.send_task("remote.unregistered", serializer="unavailable-serializer")
            except SerializerNotInstalled:
                observed_contexts.append((outer, trace.get_current_span()))

        before_task_publish.connect(publish_nested, weak=False)
        self.addCleanup(before_task_publish.disconnect, publish_nested)
        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span("parent") as parent:
            app.send_task(task_add.name, args=(1, 2), queue="publish-cleanup", ignore_result=True)
            self.assertIs(trace.get_current_span(), parent)

        self.assertEqual(len(observed_contexts), 1)
        before, after = observed_contexts[0]
        self.assertIs(before, after)
        inner, outer, finished_parent = self.memory_exporter.get_finished_spans()
        self.assertEqual(inner.name, "apply_async/remote.unregistered")
        self.assertEqual(inner.status.status_code, StatusCode.ERROR)
        self.assertEqual(inner.parent.span_id, outer.context.span_id)
        self.assertEqual(outer.status.status_code, StatusCode.UNSET)
        self.assertEqual(outer.parent.span_id, finished_parent.context.span_id)

    def test_nonrecording_publish_failure_restores_context(self) -> None:
        provider = TracerProvider(sampler=ALWAYS_OFF)
        self.addCleanup(provider.shutdown)
        CeleryInstrumentor().uninstrument()
        CeleryInstrumentor().instrument(tracer_provider=provider)
        tracer = provider.get_tracer(__name__)
        with tracer.start_as_current_span("parent") as parent:
            with self.assertRaises(SerializerNotInstalled):
                task_add.apply_async(args=(1, 2), serializer="unavailable-serializer")
            self.assertIs(trace.get_current_span(), parent)
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
