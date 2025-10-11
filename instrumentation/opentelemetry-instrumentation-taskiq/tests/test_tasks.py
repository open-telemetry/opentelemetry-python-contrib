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

import asyncio

from wrapt import wrap_function_wrapper

from opentelemetry import baggage, context
from opentelemetry.instrumentation.taskiq import TaskiqInstrumentor, utils
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode

from .taskiq_test_tasks import (
    broker,
    task_add,
    task_raises,
    task_returns_baggage,
)


class TestTaskiqInstrumentation(TestBase):
    def tearDown(self):
        super().tearDown()
        TaskiqInstrumentor().uninstrument_broker(broker)

    def test_task(self):
        TaskiqInstrumentor().instrument_broker(broker)

        async def test():
            await task_add.kiq(1, 2)
            await broker.wait_all()

        asyncio.run(test())

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(
            consumer.name,
            "execute/tests.taskiq_test_tasks:task_add",
            f"{consumer._end_time}:{producer._end_time}",
        )
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "taskiq.action": "execute",
                "taskiq.task_name": "tests.taskiq_test_tasks:task_add",
            },
        )

        self.assertEqual(consumer.status.status_code, StatusCode.UNSET)

        self.assertEqual(0, len(consumer.events))

        self.assertEqual(
            producer.name, "send/tests.taskiq_test_tasks:task_add"
        )
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "taskiq.action": "send",
                "taskiq.task_name": "tests.taskiq_test_tasks:task_add",
            },
        )

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)

    def test_task_raises(self):
        TaskiqInstrumentor().instrument_broker(broker)

        async def test():
            await task_raises.kiq()
            await broker.wait_all()

        asyncio.run(test())

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(
            consumer.name, "execute/tests.taskiq_test_tasks:task_raises"
        )
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "taskiq.action": "execute",
                "taskiq.task_name": "tests.taskiq_test_tasks:task_raises",
            },
        )

        self.assertEqual(consumer.status.status_code, StatusCode.ERROR)

        self.assertEqual(1, len(consumer.events))
        event = consumer.events[0]

        self.assertIn(SpanAttributes.EXCEPTION_STACKTRACE, event.attributes)

        self.assertEqual(
            event.attributes[SpanAttributes.EXCEPTION_TYPE],
            "tests.taskiq_test_tasks.CustomError",
        )

        self.assertEqual(
            event.attributes[SpanAttributes.EXCEPTION_MESSAGE],
            "The task failed!",
        )

        self.assertEqual(
            producer.name, "send/tests.taskiq_test_tasks:task_raises"
        )
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "taskiq.action": "send",
                "taskiq.task_name": "tests.taskiq_test_tasks:task_raises",
            },
        )

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)

    def test_uninstrument(self):
        TaskiqInstrumentor().instrument_broker(broker)
        TaskiqInstrumentor().uninstrument_broker(broker)

        async def test():
            await task_add.kiq(1, 2)
            await broker.wait_all()

        asyncio.run(test())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_baggage(self):
        TaskiqInstrumentor().instrument_broker(broker)

        ctx = baggage.set_baggage("key", "value")
        context.attach(ctx)

        async def test():
            task = await task_returns_baggage.kiq()
            result = await task.wait_result(timeout=2)
            return result.return_value

        result = asyncio.run(test())

        self.assertEqual(result, {"key": "value"})

    def test_task_not_instrumented_does_not_raise(self):
        def _retrieve_context_wrapper_none_token(
            wrapped, instance, args, kwargs
        ):
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

        TaskiqInstrumentor().instrument_broker(broker)

        async def test():
            task = await task_add.kiq(1, 2)
            result = await task.wait_result(timeout=2)
            return result.return_value

        result = asyncio.run(test())

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        self.assertTrue(result)

        unwrap(utils, "retrieve_context")
