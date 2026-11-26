from opentelemetry.metrics import Counter, Histogram, get_meter
from opentelemetry.semconv._incubating.metrics.messaging_metrics import (
    MESSAGING_CLIENT_CONSUMED_MESSAGES,
    MESSAGING_CLIENT_OPERATION_DURATION,
    MESSAGING_CLIENT_SENT_MESSAGES,
    MESSAGING_PROCESS_DURATION,
)
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
    def _instrument_queue(tracer: Tracer, process_duration: Histogram | None = None, consumed_messages: Counter | None = None):
        async def wrapper(wrapped, instance, args, kwargs):
            async def consume(
                callback: Callable[[AbstractIncomingMessage], Any],
                *fargs,
                **fkwargs,
            ):
                decorated_callback = CallbackDecorator(tracer, instance, process_duration, consumed_messages).decorate(callback)
                return await wrapped(decorated_callback, *fargs, **fkwargs)

            return await consume(*args, **kwargs)

        wrapt.wrap_function_wrapper(Queue, "consume", wrapper)

    @staticmethod
    def _instrument_exchange(tracer: Tracer, operation_duration: Histogram | None = None, sent_messages: Counter | None = None):
        async def wrapper(wrapped, instance, args, kwargs):
            decorated_publish = PublishDecorator(tracer, instance, operation_duration, sent_messages).decorate(wrapped)
            return await decorated_publish(*args, **kwargs)

        wrapt.wrap_function_wrapper(Exchange, "publish", wrapper)

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider", None)
        tracer = trace.get_tracer(
            _INSTRUMENTATION_MODULE_NAME,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        meter_provider = kwargs.get("meter_provider")
        meter = get_meter(__name__, __version__, meter_provider=meter_provider)
        operation_duration = meter.create_histogram(
            name=MESSAGING_CLIENT_OPERATION_DURATION,
            unit="s",
            description="Duration of messaging operation initiated by a client or consumer library.",
        )
        sent_messages = meter.create_counter(
            name=MESSAGING_CLIENT_SENT_MESSAGES,
            unit="{message}",
            description="Number of messages producer attempted to send to the broker.",
        )
        process_duration = meter.create_histogram(
            name=MESSAGING_PROCESS_DURATION,
            unit="s",
            description="Duration of processing operation.",
        )
        consumed_messages = meter.create_counter(
            name=MESSAGING_CLIENT_CONSUMED_MESSAGES,
            unit="{message}",
            description="Number of messages that were delivered to the application.",
        )
        self._instrument_queue(tracer, process_duration, consumed_messages)
        self._instrument_exchange(tracer, operation_duration, sent_messages)

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
