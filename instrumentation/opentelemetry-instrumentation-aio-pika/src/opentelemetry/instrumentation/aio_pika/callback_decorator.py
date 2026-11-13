# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from logging import getLogger
from typing import Any

from aio_pika import Queue
from aio_pika.abc import AbstractIncomingMessage

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.aio_pika.span_builder import SpanBuilder
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Span, Tracer

_LOG = getLogger(__name__)


class CallbackDecorator:
    def __init__(
        self,
        tracer: Tracer,
        queue: Queue,
        consume_hook: Callable[[Span, AbstractIncomingMessage], Any] | None = None,
    ):
        self._tracer = tracer
        self._queue = queue
        self._consume_hook = consume_hook

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
                return await callback(message)
            headers = message.headers or {}
            ctx = propagate.extract(headers)
            token = context.attach(ctx)
            span = self._get_span(message)
            if not span:
                return await callback(message)
            try:
                with trace.use_span(span, end_on_exit=True):
                    if self._consume_hook is not None:
                        try:
                            self._consume_hook(span, message)
                        except Exception as hook_exc:  # pylint: disable=broad-except
                            _LOG.exception(
                                "Exception occurred in aio_pika consume_hook: %s",
                                hook_exc,
                            )
                    return_value = await callback(message)
            finally:
                if token:
                    context.detach(token)
            return return_value

        return decorated
