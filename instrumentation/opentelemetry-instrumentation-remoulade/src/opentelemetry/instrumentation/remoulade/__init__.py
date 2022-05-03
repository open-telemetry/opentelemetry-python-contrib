import logging
from typing import Collection

from remoulade import Middleware, broker

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.remoulade import utils
from opentelemetry.instrumentation.remoulade.package import _instruments
from opentelemetry.instrumentation.remoulade.version import __version__
from opentelemetry.propagate import extract, inject
from opentelemetry.semconv.trace import SpanAttributes

_MESSAGE_TAG_KEY = "remoulade.action"
_MESSAGE_SEND = "send"
_MESSAGE_RUN = "run"

_MESSAGE_NAME_KEY = "remoulade.actor_name"


class InstrumentationMiddleware(Middleware):
    def __init__(self, _tracer):
        self._tracer = _tracer
        self._span_registry = {}

    def before_process_message(self, _broker, message):
        trace_ctx = extract(message.options["trace_ctx"])
        retry_count = message.options.get("retries")

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
        activation.__enter__()

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
            pass

        activation.__exit__(None, None, None)
        utils.detach_span(self._span_registry, message.message_id)

    def before_enqueue(self, _broker, message, delay):
        retry_count = message.options.get("retries")

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
            pass

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()

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

        self._tracer = trace.get_tracer(__name__, __version__, tracer_provider)

        instrumentation_middleware = InstrumentationMiddleware(self._tracer)
        broker.get_broker().add_middleware(instrumentation_middleware)

    def _uninstrument(self, **kwargs):
        broker.get_broker().remove_middleware(InstrumentationMiddleware)
