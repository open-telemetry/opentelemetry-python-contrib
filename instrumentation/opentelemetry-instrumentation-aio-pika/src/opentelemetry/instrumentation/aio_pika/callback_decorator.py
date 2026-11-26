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
from typing import Any

from aio_pika import Queue
from aio_pika.abc import AbstractIncomingMessage

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Span, Tracer


class CallbackDecorator:
    def __init__(self, tracer: Tracer, queue: Queue, process_duration: Histogram | None = None, consumed_messages: Counter | None = None):
        self._tracer = tracer
        self._queue = queue
        self._process_duration = process_duration
        self._consumed_messages = consumed_messages

    def _get_span(self, message: AbstractIncomingMessage) -> Span | None:
        builder = SpanBuilder(self._tracer)
        builder.set_as_consumer()
        builder.set_operation(MessagingOperationValues.RECEIVE)
        builder.set_destination(message.exchange or message.routing_key)
        builder.set_channel(self._queue.channel)
        builder.set_message(message)
        return builder.build()

    def decorate(self, callback: Callable[[AbstractIncomingMessage], Any]) -> Callable[[AbstractIncomingMessage], Any]:
        async def decorated(message: AbstractIncomingMessage):
            if not is_instrumentation_enabled():
                metric_attrs: dict[str, str] = {
                    MESSAGING_SYSTEM: "rabbitmq",
                    MESSAGING_DESTINATION_NAME: getattr(message, "routing_key", None) or "",
                    MESSAGING_OPERATION_TYPE: "process",
                }
                if self._consumed_messages is not None:
                    self._consumed_messages.add(1, attributes=metric_attrs)
                start = default_timer()
                try:
                    return await callback(message)
                finally:
                    if self._process_duration is not None:
                        self._process_duration.record(max(default_timer() - start, 0), attributes=metric_attrs)
            headers = message.headers or {}
            ctx = propagate.extract(headers)
            token = context.attach(ctx)
            span = self._get_span(message)
            if not span:
                return await callback(message)
            try:
                with trace.use_span(span, end_on_exit=True):
                    metric_attrs: dict[str, str] = {
                        MESSAGING_SYSTEM: "rabbitmq",
                        MESSAGING_DESTINATION_NAME: getattr(message, "routing_key", None) or "",
                        MESSAGING_OPERATION_TYPE: "process",
                    }
                    if self._consumed_messages is not None:
                        self._consumed_messages.add(1, attributes=metric_attrs)
                    start = default_timer()
                    try:
                        return_value = await callback(message)
                    finally:
                        if self._process_duration is not None:
                            self._process_duration.record(max(default_timer() - start, 0), attributes=metric_attrs)
            finally:
                if token:
                    context.detach(token)
            return return_value

        return decorated
