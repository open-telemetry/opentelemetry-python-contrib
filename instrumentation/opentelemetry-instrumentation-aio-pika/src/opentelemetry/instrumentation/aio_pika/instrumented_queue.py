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
from typing import Any, Callable, Optional

from aio_pika import Queue, RobustQueue
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.queue import ConsumerTag

from opentelemetry import context, propagate, trace
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Span

from .span_builder import SpanBuilder


class InstrumentedQueue(Queue):
    def _get_callback_span(
        self, message: AbstractIncomingMessage
    ) -> Optional[Span]:
        builder = SpanBuilder()
        builder.set_as_consumer()
        builder.set_operation(MessagingOperationValues.RECEIVE)
        builder.set_destination(message.exchange or message.routing_key)
        builder.set_channel(self.channel)
        builder.set_message(message)
        return builder.build()

    def _decorate_callback(
        self, callback: Callable[[AbstractIncomingMessage], Any]
    ) -> Callable[[AbstractIncomingMessage], Any]:
        async def decorated(message: AbstractIncomingMessage):
            headers = message.headers or dict()
            ctx = propagate.extract(headers) or context.get_current()
            token = context.attach(ctx)
            span = self._get_callback_span(message)
            if not span:
                return await callback(message)
            try:
                with trace.use_span(span, end_on_exit=True):
                    return_value = await callback(message)
            finally:
                context.detach(token)
            return return_value

        return decorated

    async def consume(
        self,
        callback: Callable[[AbstractIncomingMessage], Any],
        no_ack: bool = False,
        exclusive: bool = False,
        arguments: dict = None,
        consumer_tag=None,
        timeout=None,
    ) -> ConsumerTag:
        decorated_callback = self._decorate_callback(callback)
        return await super().consume(
            decorated_callback,
            no_ack,
            exclusive,
            arguments,
            consumer_tag,
            timeout,
        )


class RobustInstrumentedQueue(RobustQueue, InstrumentedQueue):
    async def consume(
        self,
        callback: Callable[[AbstractIncomingMessage], Any],
        no_ack: bool = False,
        exclusive: bool = False,
        arguments: dict = None,
        consumer_tag=None,
        timeout=None,
        robust: bool = True,
    ) -> ConsumerTag:
        await self.connection.connected.wait()
        consumer_tag = await InstrumentedQueue.consume(
            self, callback, no_ack, exclusive, arguments, consumer_tag, timeout
        )
        if robust:
            self._consumers[consumer_tag] = dict(
                callback=callback,
                no_ack=no_ack,
                exclusive=exclusive,
                arguments=arguments,
            )
        return consumer_tag
