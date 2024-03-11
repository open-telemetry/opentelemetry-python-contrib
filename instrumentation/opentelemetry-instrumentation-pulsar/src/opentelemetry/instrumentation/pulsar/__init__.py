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

"""
Instrument `pulsar-client` to report instrumentation-pulsar produced and consumed messages

Usage
-----

..code:: python

    from opentelemetry.instrumentation.pulsar import PulsarInstrumentor

    # Instrument pulsar
    PulsarInstrumentor().instrument()

    import threading

    import pulsar
    from pulsar import ConsumerType, InitialPosition


    def main():
        client = pulsar.Client("pulsar://localhost:6650")
        print(client)
        producer = client.create_producer("sample")

        # produce messages with the current span
        producer.send(b"hello world")

        consumer = client.subscribe("sample", "consumer-1", consumer_type=ConsumerType.KeyShared, initial_position=InitialPosition.Earliest)
        # start a span with producer's trace information
        # right now, it immediately ends, in a next iteration, this should
        # end the span on every receive or consumer.close
        print(consumer.receive(1_000))

        done = threading.Event()

        # consumer as callback, this way the whole callback runs inside a span
        def consume(consumer, message):
            print('Consumer', consumer, 'Message', message)
            done.set()

        consumer2 = client.subscribe("sample", "consumer-2", message_listener=consume, consumer_type=ConsumerType.KeyShared, initial_position=InitialPosition.Earliest)
        consumer2.resume_message_listener()

        done.wait()
        consumer2.close()
        consumer.close()

        producer.close()
        client.close()
"""
import contextlib
import inspect
from functools import wraps
from typing import Collection, Optional

import pulsar
import wrapt
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import propagator, unwrap
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Span, SpanKind, Tracer
from pulsar import Client, Consumer, Message, Producer

from opentelemetry import propagate, trace
from .package import _instruments
from .utils import (
    _enrich_span,
    _enrich_span_with_message,
    _enrich_span_with_message_id,
    _get_span_name,
)
from .version import __version__

MESSAGE_LISTENER_ARGUMENT = "message_listener"
PROPERTIES_KEY = "properties"


class _TracerMixin:
    _tracer: Tracer

    def _set_tracer(self, tracer):
        self._tracer = tracer


class _SpanMixin:
    _current_span: Optional[Span] = None

    def _set_current_span(self, current_span):
        self._current_span = current_span

    def _end_span(self):
        if self._current_span:
            with contextlib.suppress(Exception):
                self._current_span.end()
                self._current_span = None


class _InstrumentedClient(_TracerMixin, Client):
    _subscribe_signature = inspect.signature(Client.subscribe)

    def subscribe(self, topic, *args, **kwargs):
        bound_arguments = self._subscribe_signature.bind(
            self, topic, *args, **kwargs
        )
        bound_arguments.apply_defaults()

        message_listener = bound_arguments.arguments[MESSAGE_LISTENER_ARGUMENT]
        if message_listener:
            bound_arguments.arguments[
                MESSAGE_LISTENER_ARGUMENT
            ] = wrap_message_listener(topic, self._tracer, message_listener)
        # no need of self
        args = bound_arguments.args[1:]
        return super().subscribe(*args, **bound_arguments.kwargs)


def wrap_message_listener(topic, tracer, message_listener):
    @wraps(message_listener)
    def wrapper(  # pylint: disable=function-redefined
            consumer, message: "_InstrumentedMessage", *args, **kwargs
    ):
        ctx = propagator.extract(message.properties())
        span = tracer.start_span(f"receive {topic}", ctx, SpanKind.CONSUMER)
        _enrich_span(
            span,
            topic,
            MessagingOperationValues.RECEIVE,
            message.partition_key(),
        )
        _enrich_span_with_message(span, message)
        with trace.use_span(span, True):
            return message_listener(consumer, message, *args, **kwargs)

    return wrapper


class _InstrumentedProducer(_TracerMixin, Producer):
    _send_signature = inspect.signature(Producer.send)
    _send_async_signature = inspect.signature(Producer.send_async)

    def send(self, *args, **kwargs):
        with self._create_span() as span:
            args, kwargs = self._before_send(
                self._send_signature, span, *args, **kwargs
            )
            message: pulsar.MessageId = super().send(*args, **kwargs)
            return self._after_send(message, span)

    send.__doc__ = Producer.send.__doc__

    def send_async(self, content, callback, *args, **kwargs):
        with self._create_span("send_async") as span:
            args, kwargs = self._before_send(
                self._send_async_signature,
                span,
                content,
                callback,
                *args,
                **kwargs,
            )
            # As this is an async code, it is better not to rely on thread locals for span acquisition.
            carrier = {}
            propagator.inject(carrier)
            wrapper = self._wrap_send_async_callback(callback, carrier)

            super().send_async(content, wrapper, *args[2:], **kwargs)

    def _wrap_send_async_callback(self, callback, context_carrier):
        @wraps(callback)
        def wrapper(_response, message_id, *args, **kwargs):
            callback_context = propagator.extract(context_carrier)
            with self._tracer.start_as_current_span(
                    "callback", callback_context
            ) as span:
                self._after_send(message_id, span)
                return callback(_response, message_id, *args, **kwargs)

        return wrapper

    send_async.__doc__ = Producer.send_async.__doc__

    @staticmethod
    def _after_send(message, span):
        _enrich_span_with_message_id(span, message)
        return message

    def _before_send(self, signature, span, *args, **kwargs):
        bound_arguments = signature.bind(self, *args, **kwargs)
        bound_arguments.apply_defaults()

        properties = bound_arguments.arguments[PROPERTIES_KEY] or {}
        propagator.inject(properties)

        bound_arguments.arguments[PROPERTIES_KEY] = properties
        _enrich_span(
            span,
            self.topic(),
            operation=MessagingOperationValues.RECEIVE,
            **bound_arguments.arguments,
        )
        return bound_arguments.args[1:], bound_arguments.kwargs

    def _create_span(self, operation="send"):
        return self._tracer.start_as_current_span(
            name=_get_span_name(operation, self.topic()),
            kind=trace.SpanKind.PRODUCER,
        )


class _InstrumentedMessage(Message, _SpanMixin):
    pass


class _InstrumentedConsumer(_TracerMixin, Consumer):
    _last_message: _InstrumentedMessage = None

    def receive(self, *args, **kwargs):
        if self._last_message:
            self._last_message._end_span()
        with self._tracer.start_as_current_span(
                "recv", end_on_exit=False, kind=trace.SpanKind.CONSUMER
        ):
            message: _InstrumentedMessage = super().receive(*args, **kwargs)
            context = propagate.extract(message.properties())
            span = self._tracer.start_span(
                f"{self.topic()} process", context=context
            )
            _enrich_span(
                span, self.topic(), operation=MessagingOperationValues.PROCESS
            )
            message._set_current_span(span)  # pylint: disable=no-member
            self._last_message = message

            return message

    def acknowledge(self, message: _InstrumentedMessage):
        message._end_span()
        super().acknowledge(message)

    acknowledge.__doc__ = Consumer.acknowledge.__doc__

    def negative_acknowledge(self, message: _InstrumentedMessage):
        message._end_span()
        super().negative_acknowledge(message)

    negative_acknowledge.__doc__ = Consumer.negative_acknowledge.__doc__

    def acknowledge_cumulative(self, message: _InstrumentedMessage):
        message._end_span()
        super().acknowledge_cumulative(message)

    acknowledge_cumulative.__doc__ = Consumer.acknowledge_cumulative.__doc__


class PulsarInstrumentor(BaseInstrumentor):
    """An instrumentor for pulsar module
    See `BaseInstrumentor`
    """

    _original_pulsar_producer = None
    _original_pulsar_client = None
    _original_pulsar_consumer = None
    _original_pulsar_message = None
    _tracer = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        self._original_pulsar_producer = pulsar.Producer
        self._original_pulsar_client = pulsar.Client
        self._original_pulsar_consumer = pulsar.Consumer
        self._original_pulsar_message = pulsar.Message

        pulsar.Client = _InstrumentedClient
        pulsar.Producer = _InstrumentedProducer
        pulsar.Consumer = _InstrumentedConsumer
        pulsar.Message = _InstrumentedMessage

        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        self._tracer = tracer

        def init(wrapped, self, args, kwargs):
            wrapped(*args, **kwargs)
            self._set_tracer(tracer)

        wrapt.wrap_function_wrapper(_InstrumentedClient, "__init__", init)
        wrapt.wrap_function_wrapper(_InstrumentedConsumer, "__init__", init)
        wrapt.wrap_function_wrapper(_InstrumentedProducer, "__init__", init)

    def _uninstrument(self, **kwargs):
        pulsar.Client = self._original_pulsar_client
        pulsar.Producer = self._original_pulsar_producer
        pulsar.Consumer = self._original_pulsar_consumer
        pulsar.Message = self._original_pulsar_message

        unwrap(_InstrumentedClient, "__init__")
        unwrap(_InstrumentedConsumer, "__init__")
        unwrap(_InstrumentedProducer, "__init__")


__all__ = ("PulsarInstrumentor",)
