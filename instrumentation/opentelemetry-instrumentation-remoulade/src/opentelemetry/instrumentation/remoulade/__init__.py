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
Usage
-----

* Start broker backend

::

    docker run -p 5672:5672 rabbitmq

* Run instrumented actor

.. code-block:: python

    from remoulade.brokers.rabbitmq import RabbitmqBroker
    import remoulade

    RemouladeInstrumentor().instrument()

    broker = RabbitmqBroker()
    remoulade.set_broker(broker)

    @remoulade.actor
    def multiply(x, y):
        return x * y

    broker.declare_actor(count_words)

    multiply.send(43, 51)

"""
from typing import Collection, Iterable, List, Optional

from remoulade import Middleware, broker

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.remoulade import utils
from opentelemetry.instrumentation.remoulade.package import _instruments
from opentelemetry.instrumentation.remoulade.version import __version__
from opentelemetry.propagate import extract, inject
from opentelemetry.propagators.textmap import CarrierT, Getter
from opentelemetry.semconv.trace import SpanAttributes

_MESSAGE_TAG_KEY = "remoulade.action"
_MESSAGE_SEND = "send"
_MESSAGE_RUN = "run"

_MESSAGE_NAME_KEY = "remoulade.actor_name"


class RemouladeGetter(Getter):
    def get(self, carrier: CarrierT, key: str) -> Optional[str]:
        value = carrier.get(key, None)
        if value is None:
            return None
        if isinstance(value, str) or not isinstance(value, Iterable):
            value = (value,)
        return value

    def keys(self, carrier: CarrierT) -> List[str]:
        return []


remoulade_getter = RemouladeGetter()


class InstrumentationMiddleware(Middleware):
    def __init__(self, _tracer):
        self._tracer = _tracer
        self._span_registry = {}

    def before_process_message(self, _broker, message):
        if "trace_ctx" not in message.options:
            return

        trace_ctx = extract(
            message.options["trace_ctx"], getter=remoulade_getter
        )
        retry_count = message.options.get("retries", None)

        operation_name = (
            "remoulade/process"
            if retry_count is None
            else f"remoulade/process(retry-{retry_count})"
        )

        span = self._tracer.start_span(
            operation_name, kind=trace.SpanKind.CONSUMER, context=trace_ctx
        )

        if retry_count is not None:
            span.set_attribute("retry_count", retry_count)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=E1101

        utils.attach_span(
            self._span_registry, message.message_id, (span, activation)
        )

    def after_process_message(
        self, _broker, message, *, result=None, exception=None
    ):
        span, activation = utils.retrieve_span(
            self._span_registry, message.message_id
        )

        if span is None:
            # no existing span found for message_id
            return

        if span.is_recording():
            span.set_attribute(_MESSAGE_TAG_KEY, _MESSAGE_RUN)
            span.set_attribute(_MESSAGE_NAME_KEY, message.actor_name)

        activation.__exit__(None, None, None)
        utils.detach_span(self._span_registry, message.message_id)

    def before_enqueue(self, _broker, message, delay):
        retry_count = message.options.get("retries", None)

        operation_name = (
            "remoulade/send"
            if retry_count is None
            else f"remoulade/send(retry-{retry_count})"
        )

        span = self._tracer.start_span(
            operation_name, kind=trace.SpanKind.PRODUCER
        )

        if retry_count is not None:
            span.set_attribute("retry_count", retry_count)

        if span.is_recording():
            span.set_attribute(_MESSAGE_TAG_KEY, _MESSAGE_SEND)
            span.set_attribute(
                SpanAttributes.MESSAGING_MESSAGE_ID, message.message_id
            )
            span.set_attribute(_MESSAGE_NAME_KEY, message.actor_name)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=E1101

        utils.attach_span(
            self._span_registry,
            message.message_id,
            (span, activation),
            is_publish=True,
        )

        if "trace_ctx" not in message.options:
            message.options["trace_ctx"] = {}
        inject(message.options["trace_ctx"])

    def after_enqueue(self, _broker, message, delay, exception=None):
        _, activation = utils.retrieve_span(
            self._span_registry, message.message_id, is_publish=True
        )

        if activation is None:
            # no existing span found for message_id
            return

        activation.__exit__(None, None, None)
        utils.detach_span(
            self._span_registry, message.message_id, is_publish=True
        )


class RemouladeInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")

        # pylint: disable=attribute-defined-outside-init
        self._tracer = trace.get_tracer(__name__, __version__, tracer_provider)
        instrumentation_middleware = InstrumentationMiddleware(self._tracer)

        broker.add_extra_default_middleware(instrumentation_middleware)

    def _uninstrument(self, **kwargs):
        broker.remove_extra_default_middleware(InstrumentationMiddleware)
