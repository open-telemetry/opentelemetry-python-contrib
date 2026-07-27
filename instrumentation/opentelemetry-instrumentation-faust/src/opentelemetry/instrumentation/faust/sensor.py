# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional
from weakref import WeakKeyDictionary

from faust.sensors.base import Sensor

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.faust.utils import (
    _build_process_attributes,
    _build_send_attributes,
    _deserialize_key,
    _faust_getter,
    _faust_setter,
    _get_span_name,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode

if TYPE_CHECKING:
    from faust.types import AppT, EventT, StreamT
    from faust.types.transports import ProducerT
    from faust.types.tuples import TP, PendingMessage, RecordMetadata

    from opentelemetry.trace import Span, Tracer

    ProduceHookT = Optional[Callable[[Span, PendingMessage], None]]
    ProcessHookT = Optional[Callable[[Span, EventT], None]]

_LOG = getLogger(__name__)


class OpenTelemetrySensor(Sensor):  # pylint: disable=too-many-ancestors
    """A faust sensor that records spans for messages sent to Kafka and
    for events processed by faust streams.

    Instances of this sensor are added automatically to every
    ``faust.App`` created after calling
    ``FaustInstrumentor().instrument()``.
    """

    def __init__(
        self,
        tracer: Tracer,
        produce_hook: ProduceHookT = None,
        process_hook: ProcessHookT = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._tracer = tracer
        self._produce_hook = produce_hook
        self._process_hook = process_hook
        # Per-stream state for the event currently being processed.  Kept
        # so that spans are finished even when faust does not call
        # ``on_stream_event_out`` (e.g. for streams with acks disabled).
        self._stream_states: WeakKeyDictionary[StreamT, Dict] = (
            WeakKeyDictionary()
        )

    def on_send_initiated(
        self,
        producer: ProducerT,
        topic: str,
        message: PendingMessage,
        keysize: int,
        valsize: int,
    ) -> Any:
        """Start a producer span and inject its context into the message
        headers, just before a message is sent to Kafka."""
        app = producer.app
        span = self._tracer.start_span(
            _get_span_name("send", topic),
            kind=SpanKind.PRODUCER,
            attributes=_build_send_attributes(
                broker_urls=app.conf.broker,
                client_id=app.conf.broker_client_id,
                topic=topic,
                partition=message.partition,
                key=_deserialize_key(message.key),
            ),
        )
        propagate.inject(
            message.headers,
            context=trace.set_span_in_context(span),
            setter=_faust_setter,
        )
        try:
            if self._produce_hook is not None:
                self._produce_hook(span, message)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        return span

    def on_send_completed(
        self, producer: ProducerT, state: Any, metadata: RecordMetadata
    ) -> None:
        """End the producer span once the broker acknowledged the message."""
        span = state
        if isinstance(span, trace.Span):
            span.end()

    def on_send_error(
        self, producer: ProducerT, exc: BaseException, state: Any
    ) -> None:
        """End the producer span with an error status."""
        span = state
        if isinstance(span, trace.Span):
            if span.is_recording():
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                if isinstance(exc, Exception):
                    span.record_exception(exc)
            span.end()

    def on_stream_event_in(
        self, tp: TP, offset: int, stream: StreamT, event: EventT
    ) -> Optional[Dict]:
        """Start a consumer span when a stream starts processing an event.

        The span context is attached so that any span started while the
        event is being processed (including producer spans for messages
        sent from the processing agent) becomes a child of it.
        """
        # finish any span left dangling because faust never called
        # on_stream_event_out for the previous event of this stream
        self._finalize_state(self._stream_states.pop(stream, None))

        app: AppT = stream.app
        extracted_context = propagate.extract(
            event.headers, getter=_faust_getter
        )
        span = self._tracer.start_span(
            _get_span_name("process", tp.topic),
            context=extracted_context,
            kind=SpanKind.CONSUMER,
            attributes=_build_process_attributes(
                broker_urls=app.conf.broker,
                client_id=app.conf.broker_client_id,
                consumer_group=app.conf.id,
                topic=tp.topic,
                partition=tp.partition,
                offset=offset,
                key=_deserialize_key(event.message.key),
            ),
        )
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
        try:
            if self._process_hook is not None:
                self._process_hook(span, event)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        state = {"span": span, "token": token, "context": new_context}
        self._stream_states[stream] = state
        return state

    def on_stream_event_out(
        self,
        tp: TP,
        offset: int,
        stream: StreamT,
        event: EventT,
        state: Dict = None,
    ) -> None:
        """End the consumer span when the stream is done processing."""
        stored_state = self._stream_states.pop(stream, None)
        self._finalize_state(state if state else stored_state)

    @staticmethod
    def _finalize_state(state: Optional[Dict]) -> None:
        if not state:
            return
        token = state.pop("token", None)
        attached_context = state.pop("context", None)
        # Only detach when the context attached in on_stream_event_in is
        # still the active one.  When a stream is closed mid-processing
        # (worker shutdown, agent crash) this runs in a different context
        # where the token is not valid.
        if token is not None and attached_context is context.get_current():
            context.detach(token)
        span = state.pop("span", None)
        if span is not None:
            span.end()
