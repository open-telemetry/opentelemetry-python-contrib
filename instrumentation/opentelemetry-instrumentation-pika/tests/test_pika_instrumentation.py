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
from unittest import TestCase, mock

from pika.adapters import BaseConnection, BlockingConnection
from pika.adapters.blocking_connection import (
    BlockingChannel,
    _QueueConsumerGeneratorInfo,
)
from pika.channel import Channel
from pika.connection import Connection
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.pika import PikaInstrumentor
from opentelemetry.instrumentation.pika.pika_instrumentor import (
    _consumer_callback_attribute_name,
)
from opentelemetry.instrumentation.pika.utils import (
    ReadyMessagesDequeProxy,
    dummy_callback,
)
from opentelemetry.trace import Tracer


class TestPika(TestCase):
    def setUp(self) -> None:
        self.blocking_channel = mock.MagicMock(spec=BlockingChannel)
        self.channel = mock.MagicMock(spec=Channel)
        consumer_info = mock.MagicMock()
        callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR
        setattr(consumer_info, callback_attr, mock.MagicMock())
        self.blocking_channel._consumer_infos = {"consumer-tag": consumer_info}
        self.channel._consumers = {"consumer-tag": consumer_info}
        self.mock_callback = mock.MagicMock()

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
        assert hasattr(
            instrumentation, "__opentelemetry_tracer_provider"
        ), "Tracer not stored for the object!"
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
        assert hasattr(
            self.channel, "_is_instrumented_by_opentelemetry"
        ), "channel is not marked as instrumented!"
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
            hasattr(callback, "_original_callback")
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
            hasattr(callback, "_original_callback")
            for callback in self.channel._consumers.values()
        )

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
