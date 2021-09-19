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

from pika.adapters import BaseConnection
from pika.channel import Channel

from opentelemetry.instrumentation.pika import PikaInstrumentor
from opentelemetry.trace import Tracer


class TestPika(TestCase):
    def setUp(self) -> None:
        self.channel = mock.MagicMock(spec=Channel)
        self.channel._impl = mock.MagicMock(spec=BaseConnection)
        self.mock_callback = mock.MagicMock()
        self.channel._impl._consumers = {"mock_key": self.mock_callback}

    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor.instrument_channel"
    )
    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._uninstrument_channel_functions"
    )
    def test_instrument_api(
        self,
        uninstrument_channel_functions: mock.MagicMock,
        instrument_channel: mock.MagicMock,
    ) -> None:
        instrumentation = PikaInstrumentor()
        instrumentation.instrument(channel=self.channel)
        instrument_channel.assert_called_once_with(
            self.channel, tracer_provider=None
        )
        self.channel._impl._consumers = {"mock_key": mock.MagicMock()}
        self.channel._impl._consumers[
            "mock_key"
        ]._original_callback = self.mock_callback
        instrumentation.uninstrument(channel=self.channel)
        uninstrument_channel_functions.assert_called_once()
        self.assertEqual(
            self.channel._impl._consumers["mock_key"], self.mock_callback
        )

    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._instrument_channel_functions"
    )
    @mock.patch(
        "opentelemetry.instrumentation.pika.PikaInstrumentor._instrument_consumers"
    )
    def test_instrument(
        self,
        instrument_consumers: mock.MagicMock,
        instrument_channel_functions: mock.MagicMock,
    ):
        PikaInstrumentor.instrument_channel(channel=self.channel)
        assert hasattr(
            self.channel, "__opentelemetry_tracer"
        ), "Tracer not set for the channel!"
        instrument_consumers.assert_called_once()
        instrument_channel_functions.assert_called_once()

    @mock.patch("opentelemetry.instrumentation.pika.utils.decorate_callback")
    def test_instrument_consumers(
        self, decorate_callback: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        expected_decoration_calls = [
            mock.call(value, tracer, key)
            for key, value in self.channel._impl._consumers.items()
        ]
        PikaInstrumentor._instrument_consumers(
            self.channel._impl._consumers, tracer
        )
        decorate_callback.assert_has_calls(
            calls=expected_decoration_calls, any_order=True
        )
        assert all(
            hasattr(callback, "_original_callback")
            for callback in self.channel._impl._consumers.values()
        )

    @mock.patch(
        "opentelemetry.instrumentation.pika.utils.decorate_basic_publish"
    )
    def test_instrument_basic_publish(
        self, decorate_basic_publish: mock.MagicMock
    ) -> None:
        tracer = mock.MagicMock(spec=Tracer)
        original_function = self.channel.basic_publish
        PikaInstrumentor._instrument_basic_publish(self.channel, tracer)
        decorate_basic_publish.assert_called_once_with(
            original_function, self.channel, tracer
        )
        self.assertEqual(
            self.channel.basic_publish, decorate_basic_publish.return_value
        )
        self.assertEqual(
            self.channel.basic_publish._original_function, original_function
        )

    def test_uninstrument_channel_functions(self) -> None:
        original_function = self.channel.basic_publish
        self.channel.basic_publish = mock.MagicMock()
        self.channel.basic_publish._original_function = original_function
        PikaInstrumentor._uninstrument_channel_functions(self.channel)
        self.assertEqual(self.channel.basic_publish, original_function)
