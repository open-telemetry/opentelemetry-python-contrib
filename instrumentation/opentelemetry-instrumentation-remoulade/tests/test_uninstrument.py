import remoulade
from remoulade.brokers.local import LocalBroker

from opentelemetry.instrumentation.remoulade import RemouladeInstrumentor
from opentelemetry.test.test_base import TestBase


@remoulade.actor(max_retries=3)
def actor_div(x, y):
    return x / y


class TestRemouladeUninstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        RemouladeInstrumentor().instrument()

        broker = LocalBroker()
        remoulade.set_broker(broker)
        broker.declare_actor(actor_div)

        RemouladeInstrumentor().uninstrument()

    def test_uninstrument_existing_broker(self):
        actor_div.send(1, 1)
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 0)

    def test_uninstrument_new_brokers(self):
        new_broker = LocalBroker()
        remoulade.set_broker(new_broker)
        new_broker.declare_actor(actor_div)

        actor_div.send(1, 1)
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 0)

    def test_reinstrument_existing_broker(self):
        RemouladeInstrumentor().instrument()

        actor_div.send(1, 1)
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)
