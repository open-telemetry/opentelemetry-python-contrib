# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from collections import Counter
from types import SimpleNamespace
from unittest import TestCase, mock

from pika.adapters import BaseConnection, BlockingConnection
from pika.adapters.blocking_connection import (
    BlockingChannel,
    _QueueConsumerGeneratorInfo,
)
from pika.channel import Channel
from pika.connection import Connection
from pika.spec import BasicProperties
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.pika import PikaInstrumentor
from opentelemetry.instrumentation.pika.pika_instrumentor import (
    _consumer_callback_attribute_name,
)
from opentelemetry.instrumentation.pika.utils import (
    ReadyMessagesDequeProxy,
    dummy_callback,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind, Tracer


class TestPika(TestCase):
    def setUp(self) -> None:
        self.blocking_channel = mock.MagicMock(spec=BlockingChannel)
        self.channel = mock.MagicMock(spec=Channel)
        consumer_info = mock.MagicMock()
        callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR
        setattr(consumer_info, callback_attr, self._consumer_callback)
        self.blocking_channel._consumer_infos = {"consumer-tag": consumer_info}
        self.channel._consumers = {"consumer-tag": consumer_info}
        self.mock_callback = mock.MagicMock()

    @staticmethod
    def _consumer_callback(
        channel: object, method: object, properties: object, body: object
    ) -> None:
        pass

    def test_instrument_api(self) -> None:
        instrumentation = PikaInstrumentor()
        instrumentation.instrument()
        self.assertTrue(
            isinstance(BlockingConnection.channel, BoundFunctionWrapper)
        )
        self.assertTrue(isinstance(Connection.channel, BoundFunctionWrapper))
        self.assertTrue(
            isinstance(BaseConnection.channel, BoundFunctionWrapper)
        )
        self.assertTrue(
            isinstance(
                _QueueConsumerGeneratorInfo.__init__, BoundFunctionWrapper
            )
        )
        assert hasattr(instrumentation, "__opentelemetry_tracer_provider"), (
            "Tracer not stored for the object!"
        )
        instrumentation.uninstrument()
        self.assertFalse(
            isinstance(BlockingConnection.channel, BoundFunctionWrapper)
        )
        self.assertFalse(isinstance(Connection.channel, BoundFunctionWrapper))
        self.assertFalse(
            isinstance(BaseConnection.channel, BoundFunctionWrapper)
        )
        self.assertFalse(
            isinstance(
                _QueueConsumerGeneratorInfo.__init__, BoundFunctionWrapper
            )
        )

    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._instrument_channel_functions"
    )
    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._decorate_basic_consume"
    )
    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._instrument_channel_consumers"
    )
    def test_instrument_blocking_channel(
        self,
        instrument_channel_consumers: mock.MagicMock,
        instrument_basic_consume: mock.MagicMock,
        instrument_channel_functions: mock.MagicMock,
    ):
        PikaInstrumentor.instrument_channel(channel=self.blocking_channel)
        assert hasattr(
            self.blocking_channel, "_is_instrumented_by_opentelemetry"
        ), "channel is not marked as instrumented!"
        instrument_channel_consumers.assert_called_once()
        instrument_basic_consume.assert_called_once()
        instrument_channel_functions.assert_called_once()

    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._instrument_channel_functions"
    )
    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._decorate_basic_consume"
    )
    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._instrument_channel_consumers"
    )
    def test_instrument_channel(
        self,
        instrument_channel_consumers: mock.MagicMock,
        instrument_basic_consume: mock.MagicMock,
        instrument_channel_functions: mock.MagicMock,
    ):
        PikaInstrumentor.instrument_channel(channel=self.channel)
        assert hasattr(self.channel, "_is_instrumented_by_opentelemetry"), (
            "channel is not marked as instrumented!"
        )
        instrument_channel_consumers.assert_called_once()
        instrument_basic_consume.assert_called_once()
        instrument_channel_functions.assert_called_once()

    @mock.patch("opentelemetry.instrumentation.pika.utils._decorate_callback")
    def test_instrument_consumers_on_blocking_channel(
        self, decorate_callback: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR
        expected_decoration_calls = [
            mock.call(
                getattr(value, callback_attr), tracer, key, dummy_callback
            )
            for key, value in self.blocking_channel._consumer_infos.items()
        ]
        PikaInstrumentor._instrument_channel_consumers(
            self.blocking_channel, tracer
        )
        decorate_callback.assert_has_calls(
            calls=expected_decoration_calls, any_order=True
        )
        assert all(
            hasattr(
                getattr(callback, callback_attr),
                "_original_callback",
            )
            for callback in self.blocking_channel._consumer_infos.values()
        )

    @mock.patch("opentelemetry.instrumentation.pika.utils._decorate_callback")
    def test_instrument_consumers_on_channel(
        self, decorate_callback: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR
        expected_decoration_calls = [
            mock.call(
                getattr(value, callback_attr), tracer, key, dummy_callback
            )
            for key, value in self.channel._consumers.items()
        ]
        PikaInstrumentor._instrument_channel_consumers(self.channel, tracer)
        decorate_callback.assert_has_calls(
            calls=expected_decoration_calls, any_order=True
        )
        assert all(
            hasattr(
                getattr(callback, callback_attr),
                "_original_callback",
            )
            for callback in self.channel._consumers.values()
        )

    @mock.patch("opentelemetry.instrumentation.pika.utils._decorate_callback")
    def test_instrument_consumers_skips_already_decorated_callbacks(
        self, decorate_callback: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR

        for channel, consumer_infos in (
            (self.blocking_channel, self.blocking_channel._consumer_infos),
            (self.channel, self.channel._consumers),
        ):
            with self.subTest(channel=channel):
                decorated_consumer_info = mock.MagicMock()

                def decorated_callback(
                    channel: object,
                    method: object,
                    properties: object,
                    body: object,
                ) -> None:
                    pass

                decorated_callback._original_callback = self._consumer_callback
                setattr(
                    decorated_consumer_info,
                    callback_attr,
                    decorated_callback,
                )
                new_consumer_info = mock.MagicMock()
                setattr(
                    new_consumer_info,
                    callback_attr,
                    self._consumer_callback,
                )
                consumer_infos.clear()
                consumer_infos.update(
                    {
                        "decorated-consumer-tag": decorated_consumer_info,
                        "new-consumer-tag": new_consumer_info,
                    }
                )

                PikaInstrumentor._instrument_channel_consumers(channel, tracer)

                decorate_callback.assert_called_once_with(
                    self._consumer_callback,
                    tracer,
                    "new-consumer-tag",
                    dummy_callback,
                )
                self.assertIs(
                    getattr(decorated_consumer_info, callback_attr),
                    decorated_callback,
                )
                self.assertIs(
                    getattr(new_consumer_info, callback_attr),
                    decorate_callback.return_value,
                )

                decorate_callback.reset_mock()

    def test_sequential_basic_consume_registrations_do_not_duplicate_spans(
        self,
    ) -> None:
        callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR
        memory_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(memory_exporter)
        )
        tracer = tracer_provider.get_tracer(__name__)

        callback_calls = []

        def on_msg(
            channel: object,
            method: object,
            properties: object,
            body: object,
        ) -> None:
            callback_calls.append((channel, method, properties, body))
            channel.basic_ack(method.delivery_tag)

        class FakeBlockingChannel:
            def __init__(self) -> None:
                self._consumer_infos = {}
                self.connection = SimpleNamespace(
                    params=SimpleNamespace(host="localhost", port=5672)
                )
                self.basic_ack = mock.MagicMock()

            @property
            def __class__(self):
                return BlockingChannel

            def basic_consume(
                self, queue: str, *args: object, **kwargs: object
            ) -> str:
                consumer_callback = (
                    kwargs.get("on_message_callback")
                    or kwargs.get("consumer_callback")
                    or kwargs.get("consumer_cb")
                    or args[0]
                )
                self._consumer_infos[queue] = SimpleNamespace(
                    **{callback_attr: consumer_callback}
                )
                return queue

        channel = FakeBlockingChannel()
        PikaInstrumentor._decorate_basic_consume(channel, tracer)

        for queue_name in ("q1", "q2", "q3"):
            channel.basic_consume(
                queue_name,
                on_message_callback=on_msg,
            )

        method = SimpleNamespace(
            exchange="",
            routing_key="q1",
            consumer_tag="q1",
            delivery_tag=1,
        )
        properties = BasicProperties(headers={})
        q1_callback = getattr(channel._consumer_infos["q1"], callback_attr)

        q1_callback(
            channel,
            method,
            properties,
            b"hello",
        )

        spans = memory_exporter.get_finished_spans()
        self.assertEqual(
            Counter(
                span.name for span in spans if span.kind == SpanKind.CONSUMER
            ),
            Counter({"q1 receive": 1}),
        )
        self.assertEqual(
            callback_calls, [(channel, method, properties, b"hello")]
        )
        channel.basic_ack.assert_called_once_with(1)

    @mock.patch(
        "opentelemetry.instrumentation.pika.utils._decorate_basic_publish"
    )
    def test_instrument_basic_publish_on_blocking_channel(
        self, decorate_basic_publish: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        original_function = self.blocking_channel.basic_publish
        PikaInstrumentor._instrument_basic_publish(
            self.blocking_channel, tracer
        )
        decorate_basic_publish.assert_called_once_with(
            original_function, self.blocking_channel, tracer, dummy_callback
        )
        self.assertEqual(
            self.blocking_channel.basic_publish,
            decorate_basic_publish.return_value,
        )

    @mock.patch(
        "opentelemetry.instrumentation.pika.utils._decorate_basic_publish"
    )
    def test_instrument_basic_publish_on_channel(
        self, decorate_basic_publish: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        original_function = self.channel.basic_publish
        PikaInstrumentor._instrument_basic_publish(self.channel, tracer)
        decorate_basic_publish.assert_called_once_with(
            original_function, self.channel, tracer, dummy_callback
        )
        self.assertEqual(
            self.channel.basic_publish, decorate_basic_publish.return_value
        )

    def test_instrument_queue_consumer_generator(self) -> None:
        instrumentation = PikaInstrumentor()
        instrumentation.instrument()
        generator_info = _QueueConsumerGeneratorInfo(
            params=("queue", False, False), consumer_tag="tag"
        )
        self.assertTrue(
            isinstance(generator_info.pending_events, ReadyMessagesDequeProxy)
        )
        instrumentation.uninstrument()
        generator_info = _QueueConsumerGeneratorInfo(
            params=("queue", False, False), consumer_tag="tag"
        )
        self.assertFalse(
            isinstance(generator_info.pending_events, ReadyMessagesDequeProxy)
        )

    def test_uninstrument_blocking_channel_functions(self) -> None:
        original_function = self.blocking_channel.basic_publish
        self.blocking_channel.basic_publish = mock.MagicMock()
        self.blocking_channel.basic_publish._original_function = (
            original_function
        )
        PikaInstrumentor._uninstrument_channel_functions(self.blocking_channel)
        self.assertEqual(
            self.blocking_channel.basic_publish, original_function
        )

    def test_uninstrument_channel_functions(self) -> None:
        original_function = self.channel.basic_publish
        self.channel.basic_publish = mock.MagicMock()
        self.channel.basic_publish._original_function = original_function
        PikaInstrumentor._uninstrument_channel_functions(self.channel)
        self.assertEqual(self.channel.basic_publish, original_function)

    def test_consumer_callback_attribute_name(self) -> None:
        with mock.patch("pika.__version__", "1.0.0"):
            self.assertEqual(
                _consumer_callback_attribute_name(), "on_message_callback"
            )
        with mock.patch("pika.__version__", "0.12.0"):
            self.assertEqual(
                _consumer_callback_attribute_name(), "consumer_cb"
            )
