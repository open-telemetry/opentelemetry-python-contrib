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

import threading
import time

from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

from .celery_test_tasks import app, task_add


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

        self.assertEqual(
            producer.name, "apply_async/tests.celery_test_tasks.task_add"
        )
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

        self.assertEqual(
            producer.name, "apply_async/tests.test_tasks.hidden_task"
        )
        self.assertEqual(producer.kind, SpanKind.PRODUCER)

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)
