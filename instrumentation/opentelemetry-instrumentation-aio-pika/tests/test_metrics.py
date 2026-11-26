import unittest
from unittest import mock

from opentelemetry.instrumentation.aio_pika.callback_decorator import (
    CallbackDecorator,
)
from opentelemetry.instrumentation.aio_pika.publish_decorator import (
    PublishDecorator,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv._incubating.metrics.messaging_metrics import (
    MESSAGING_CLIENT_CONSUMED_MESSAGES,
    MESSAGING_CLIENT_OPERATION_DURATION,
    MESSAGING_CLIENT_SENT_MESSAGES,
    MESSAGING_PROCESS_DURATION,
)


class TestAioPikaMetrics(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_callback_metrics(self):
        reader = InMemoryMetricReader()
        meter = MeterProvider(metric_readers=[reader]).get_meter("test")
        tracer = TracerProvider().get_tracer("test")

        op_duration = meter.create_histogram(MESSAGING_CLIENT_OPERATION_DURATION, unit="s")
        sent_counter = meter.create_counter(MESSAGING_CLIENT_SENT_MESSAGES, unit="{message}")
        process_duration = meter.create_histogram(MESSAGING_PROCESS_DURATION, unit="s")
        consumed_counter = meter.create_counter(MESSAGING_CLIENT_CONSUMED_MESSAGES, unit="{message}")

        exchange = mock.MagicMock()
        exchange.name = "orders"
        exchange.channel.connection.connection.host = "localhost"
        exchange.channel.connection.connection.port = 5672

        message = mock.MagicMock()
        message.headers = {}
        message.message_id = "msg-1"
        message.correlation_id = None
        message.routing_key = "orders.created"

        async def fake_publish(msg, routing_key, *args, **kwargs):
            return "ok"

        wrapped_publish = PublishDecorator(tracer, exchange, op_duration, sent_counter).decorate(fake_publish)
        res = await wrapped_publish(message, "orders.created")
        self.assertEqual(res, "ok")

        async def fake_callback(msg):
            return "processed"

        queue = mock.MagicMock()
        wrapped_callback = CallbackDecorator(tracer, queue, process_duration, consumed_counter).decorate(fake_callback)
        cb_res = await wrapped_callback(message)
        self.assertEqual(cb_res, "processed")

        metrics_data = reader.get_metrics_data()
        metrics_by_name = {
            m.name: m
            for rm in metrics_data.resource_metrics
            for sm in rm.scope_metrics
            for m in sm.metrics
        }

        self.assertEqual(metrics_by_name[MESSAGING_CLIENT_SENT_MESSAGES].data.data_points[0].value, 1)
        self.assertEqual(metrics_by_name[MESSAGING_CLIENT_OPERATION_DURATION].data.data_points[0].count, 1)
        self.assertEqual(metrics_by_name[MESSAGING_CLIENT_CONSUMED_MESSAGES].data.data_points[0].value, 1)
        self.assertEqual(metrics_by_name[MESSAGING_PROCESS_DURATION].data.data_points[0].count, 1)
