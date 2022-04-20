import remoulade
from remoulade.brokers.local import LocalBroker
from remoulade.results import Results
from remoulade.results.backends import LocalBackend
from opentelemetry.instrumentation.remoulade import RemouladeInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind



@remoulade.actor
def actor_multiply(x, y):
    return x * y


class TestRemouladeInstrumentation(TestBase):
    def setUp(self):
        super().setUp()

        broker = LocalBroker()

        # Should a backend be added to wait for the result ?
        # result_backend = LocalBackend()
        # broker.add_middleware(Results(backend=result_backend))
        remoulade.set_broker(broker)
        RemouladeInstrumentor().instrument()

        broker.declare_actor(actor_multiply)

    def test_message(self):
        message = actor_multiply.send(1, 2)
        # result = message.result.get(block=True)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)

        consumer, producer = spans

        self.assertEqual(consumer.name, "remoulade/process")
        self.assertEqual(consumer.kind, SpanKind.CONSUMER)

        self.assertEqual(producer.name, "remoulade/send")
        self.assertEqual(producer.kind, SpanKind.PRODUCER)

        self.assertNotEqual(consumer.parent, producer.context)
        self.assertEqual(consumer.parent.span_id, producer.context.span_id)
        self.assertEqual(consumer.context.trace_id, producer.context.trace_id)