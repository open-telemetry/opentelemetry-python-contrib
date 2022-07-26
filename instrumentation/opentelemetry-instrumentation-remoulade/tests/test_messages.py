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

import remoulade
from remoulade.brokers.stub import StubBroker

from opentelemetry.instrumentation.remoulade import RemouladeInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


@remoulade.actor(max_retries=1, min_backoff=0, max_backoff=0)
def actor_div(dividend, divisor):
    return dividend / divisor


class TestRemouladeInstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        RemouladeInstrumentor().instrument()

        broker = StubBroker()
        remoulade.set_broker(broker)

        broker.declare_actor(actor_div)

        self._worker = remoulade.Worker(broker)
        self._thread = threading.Thread(target=self._worker.start)
        self._thread.daemon = True
        self._thread.start()

    def tearDown(self):
        RemouladeInstrumentor().uninstrument()
        self._worker.stop()
        self._thread.join()
        super().tearDown()

    def test_message(self):
        actor_div.send(2, 3)
        time.sleep(1)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "remoulade/process")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "remoulade.action": "run",
                "remoulade.actor_name": "actor_div",
            },
        )

        self.assertEqual(producer.name, "remoulade/send")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "remoulade.action": "send",
                "remoulade.actor_name": "actor_div",
            },
        )

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)

    def test_retries(self):
        actor_div.send(1, 0)
        time.sleep(1)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())

        self.assertEqual(len(spans), 5)

        trace_id = spans[0].context.trace_id
        self.assertEqual(spans[0].name, "remoulade/process(retry-1)")
        self.assertSpanHasAttributes(spans[0], {"remoulade.retry_count": 1})

        self.assertEqual(spans[1].context.trace_id, trace_id)
        self.assertEqual(spans[1].name, "remoulade/send(retry-1)")
        self.assertSpanHasAttributes(spans[1], {"remoulade.retry_count": 1})

        self.assertEqual(spans[2].context.trace_id, trace_id)
        self.assertEqual(spans[2].name, "remoulade/delay(retry-1)")
        self.assertSpanHasAttributes(spans[2], {"remoulade.retry_count": 1})

        self.assertEqual(spans[3].context.trace_id, trace_id)
        self.assertEqual(spans[3].name, "remoulade/process")
        self.assertSpanHasAttributes(spans[3], {"remoulade.retry_count": 0})

        self.assertEqual(spans[4].context.trace_id, trace_id)
        self.assertEqual(spans[4].name, "remoulade/send")
        self.assertSpanHasAttributes(spans[4], {"remoulade.retry_count": 0})
