from timeit import default_timer
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_DESTINATION_NAME,
    MESSAGING_OPERATION_TYPE,
    MESSAGING_SYSTEM,
)
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable

import aiormq
from aio_pika import Exchange
from aio_pika.abc import AbstractMessage

from opentelemetry import propagate, trace
from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder
from opentelemetry.trace import Span, Tracer


class PublishDecorator:
    def __init__(self, tracer: Tracer, exchange: Exchange, operation_duration: Histogram | None = None, sent_messages: Counter | None = None):
        self._tracer = tracer
        self._exchange = exchange
        self._operation_duration = operation_duration
        self._sent_messages = sent_messages

    def _get_publish_span(self, message: AbstractMessage, routing_key: str) -> Span | None:
        builder = SpanBuilder(self._tracer)
        builder.set_as_producer()
        builder.set_destination(f"{self._exchange.name},{routing_key}")
        builder.set_channel(self._exchange.channel)
        builder.set_message(message)
        return builder.build()

    def decorate(self, publish: Callable) -> Callable:
        async def decorated_publish(
            message: AbstractMessage, routing_key: str, **kwargs
        ) -> aiormq.abc.ConfirmationFrameType | None:
            span = self._get_publish_span(message, routing_key)
            if not span:
                metric_attrs: dict[str, str] = {
                    MESSAGING_SYSTEM: "rabbitmq",
                    MESSAGING_DESTINATION_NAME: self._exchange.name or "default",
                    MESSAGING_OPERATION_TYPE: "send",
                }
                start = default_timer()
                try:
                    retval = await publish(message, routing_key, **kwargs)
                finally:
                    if self._operation_duration is not None:
                        self._operation_duration.record(max(default_timer() - start, 0), attributes=metric_attrs)
                if self._sent_messages is not None:
                    self._sent_messages.add(1, attributes=metric_attrs)
                return retval
            with trace.use_span(span, end_on_exit=True):
                propagate.inject(message.properties.headers)
                metric_attrs: dict[str, str] = {
                    MESSAGING_SYSTEM: "rabbitmq",
                    MESSAGING_DESTINATION_NAME: self._exchange.name or "default",
                    MESSAGING_OPERATION_TYPE: "send",
                }
                start = default_timer()
                try:
                    return_value = await publish(message, routing_key, **kwargs)
                finally:
                    if self._operation_duration is not None:
                        self._operation_duration.record(max(default_timer() - start, 0), attributes=metric_attrs)
                if self._sent_messages is not None:
                    self._sent_messages.add(1, attributes=metric_attrs)
            return return_value

        return decorated_publish
