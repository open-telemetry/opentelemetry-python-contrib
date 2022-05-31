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
from typing import Optional

import aiormq
from aio_pika import Exchange, RobustExchange
from aio_pika.abc import AbstractMessage

from opentelemetry import propagate, trace
from opentelemetry.trace import Span

from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder


class InstrumentedExchange(Exchange):
    def _get_publish_span(
        self, message: AbstractMessage, routing_key: str
    ) -> Optional[Span]:
        builder = SpanBuilder()
        builder.set_as_producer()
        builder.set_destination(f"{self.name},{routing_key}")
        builder.set_channel(self.channel)
        builder.set_message(message)
        return builder.build()

    async def publish(
        self, message: AbstractMessage, routing_key: str, **kwargs
    ) -> Optional[aiormq.abc.ConfirmationFrameType]:
        span = self._get_publish_span(message, routing_key)
        if not span:
            return await super().publish(message, routing_key, **kwargs)
        with trace.use_span(span, end_on_exit=True):
            if span.is_recording():
                propagate.inject(message.properties.headers)
            return_value = await super().publish(
                message, routing_key, **kwargs
            )
        return return_value


class RobustInstrumentedExchange(RobustExchange, InstrumentedExchange):
    pass
