# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable, Collection
from typing import Any

import wrapt
from aio_pika import Exchange, Queue
from aio_pika.abc import AbstractIncomingMessage

from opentelemetry import trace
from opentelemetry.instrumentation.aio_pika.callback_decorator import (
    CallbackDecorator,
)
from opentelemetry.instrumentation.aio_pika.package import _instruments
from opentelemetry.instrumentation.aio_pika.publish_decorator import (
    PublishDecorator,
)
from opentelemetry.instrumentation.aio_pika.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer

_INSTRUMENTATION_MODULE_NAME = "opentelemetry.instrumentation.aio_pika"


class AioPikaInstrumentor(BaseInstrumentor):
    @staticmethod
    def _instrument_queue(tracer: Tracer, consume_hook: Callable | None = None):
        async def wrapper(wrapped, instance, args, kwargs):
            async def consume(
                callback: Callable[[AbstractIncomingMessage], Any],
                *fargs,
                **fkwargs,
            ):
                decorated_callback = CallbackDecorator(
                    tracer, instance, consume_hook=consume_hook
                ).decorate(callback)
                return await wrapped(decorated_callback, *fargs, **fkwargs)

            return await consume(*args, **kwargs)

        wrapt.wrap_function_wrapper(Queue, "consume", wrapper)

    @staticmethod
    def _instrument_exchange(tracer: Tracer, publish_hook: Callable | None = None):
        async def wrapper(wrapped, instance, args, kwargs):
            decorated_publish = PublishDecorator(
                tracer, instance, publish_hook=publish_hook
            ).decorate(wrapped)
            return await decorated_publish(*args, **kwargs)

        wrapt.wrap_function_wrapper(Exchange, "publish", wrapper)

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider", None)
        publish_hook = kwargs.get("publish_hook", None)
        consume_hook = kwargs.get("consume_hook", None)
        tracer = trace.get_tracer(
            _INSTRUMENTATION_MODULE_NAME,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        self._instrument_queue(tracer, consume_hook=consume_hook)
        self._instrument_exchange(tracer, publish_hook=publish_hook)

    @staticmethod
    def _uninstrument_queue():
        unwrap(Queue, "consume")

    @staticmethod
    def _uninstrument_exchange():
        unwrap(Exchange, "publish")

    def _uninstrument(self, **kwargs):
        self._uninstrument_queue()
        self._uninstrument_exchange()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
