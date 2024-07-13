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

from aio_pika.abc import AbstractChannel, AbstractMessage

from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.semconv._incubating.attributes import (
    messaging_attributes as SpanAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    net_attributes as NetAttributes,
)
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Span, SpanKind, Tracer

_DEFAULT_ATTRIBUTES = {SpanAttributes.MESSAGING_SYSTEM: "rabbitmq"}


class SpanBuilder:
    """
    https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/#messaging-attributes
    https://opentelemetry.io/docs/specs/semconv/messaging/rabbitmq/#rabbitmq-attributes
    """

    def __init__(self, tracer: Tracer):
        self._tracer = tracer
        self._attributes = _DEFAULT_ATTRIBUTES.copy()
        self._operation: MessagingOperationValues = None
        self._kind: SpanKind = None
        self._exchange_name: str = None
        self._routing_key: str = None

    def set_as_producer(self):
        self._kind = SpanKind.PRODUCER

    def set_as_consumer(self):
        self._kind = SpanKind.CONSUMER

    def set_operation(self, operation: MessagingOperationValues):
        self._operation = operation

    def set_destination(self, exchange_name: str, routing_key: str):
        self._exchange_name = exchange_name
        self._routing_key = routing_key
        # messaging.destination.name MUST be set to the name of the exchange.
        self._attributes[SpanAttributes.MESSAGING_DESTINATION_NAME] = (
            exchange_name
        )
        if routing_key:
            self._attributes[
                SpanAttributes.MESSAGING_RABBITMQ_DESTINATION_ROUTING_KEY
            ] = routing_key

    def set_channel(self, channel: AbstractChannel):
        if hasattr(channel, "_connection"):
            # aio_rmq 9.1 and above removed the connection attribute from the abstract listings
            connection = channel._connection
        else:
            # aio_rmq 9.0.5 and below
            connection = channel.connection
        if hasattr(connection, "connection"):
            # aio_rmq 7
            url = connection.connection.url
        else:
            # aio_rmq 8
            url = connection.url
        self._attributes.update(
            {
                NetAttributes.NET_PEER_NAME: url.host,
                NetAttributes.NET_PEER_PORT: url.port or 5672,
            }
        )

    def set_message(self, message: AbstractMessage):
        properties = message.properties
        if properties.message_id:
            self._attributes[SpanAttributes.MESSAGING_MESSAGE_ID] = (
                properties.message_id
            )
        if properties.correlation_id:
            self._attributes[
                SpanAttributes.MESSAGING_MESSAGE_CONVERSATION_ID
            ] = properties.correlation_id

    def build(self) -> Optional[Span]:
        if not is_instrumentation_enabled():
            return None
        if self._operation:
            self._attributes[SpanAttributes.MESSAGING_OPERATION_TYPE] = (
                self._operation.value
            )
        else:
            self._attributes[
                SpanAttributes.MESSAGING_DESTINATION_TEMPORARY
            ] = True
        span = self._tracer.start_span(
            self._generate_span_name(),
            kind=self._kind,
            attributes=self._attributes,
        )
        return span

    def _generate_span_name(self) -> str:
        operation_value = self._operation.value if self._operation else "send"
        return f"{self._exchange_name},{self._routing_key} {operation_value}"
