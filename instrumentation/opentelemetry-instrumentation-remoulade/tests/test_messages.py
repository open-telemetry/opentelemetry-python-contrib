import remoulade
from remoulade.brokers.local import LocalBroker
from opentelemetry.instrumentation.remoulade import RemouladeInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.trace import SpanAttributes


@remoulade.actor
def actor_multiply(x, y):
    return x * y


class TestRemouladeInstrumentation(TestBase):
    def setUp(self):
        super().setUp()

        broker = LocalBroker()

        remoulade.set_broker(broker)
        RemouladeInstrumentor().instrument()

        broker.declare_actor(actor_multiply)

    def test_message(self):
        actor_multiply.send(1, 2)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "remoulade/process")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            consumer,
            {
                "remoulade.action": "run",
                "remoulade.actor_name": "actor_multiply",
            },
        )

        self.assertEqual(producer.name, "remoulade/send")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            producer,
            {
                "remoulade.action": "send",
                "remoulade.actor_name": "actor_multiply",
            },
        )

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)