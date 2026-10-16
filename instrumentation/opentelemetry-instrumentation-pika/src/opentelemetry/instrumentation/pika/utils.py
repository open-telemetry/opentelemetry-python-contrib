# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from logging import getLogger
from typing import Any

from pika.adapters.blocking_connection import (
    _ConsumerDeliveryEvt,
    _QueueConsumerGeneratorInfo,
)
from pika.channel import Channel
from pika.spec import Basic, BasicProperties
from wrapt import ObjectProxy

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation._semconv import (
    _report_new,
    _report_old,
    _set_messaging_conversation_id,
    _set_messaging_destination,
    _set_messaging_operation,
    _set_messaging_temp_destination,
    _StabilityMode,
)
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.propagators.textmap import CarrierT, Getter
from opentelemetry.semconv._incubating.attributes import (
    messaging_attributes,
    server_attributes,
)
from opentelemetry.semconv.trace import MessagingOperationValues, SpanAttributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.span import Span
from opentelemetry.util.types import AttributeValue

_LOG = getLogger(__name__)


class _PikaGetter(Getter[CarrierT]):  # type: ignore
    def get(self, carrier: CarrierT, key: str) -> list[str] | None:
        value = carrier.get(key, None)
        if value is None:
            return None
        return [value]

    def keys(self, carrier: CarrierT) -> list[str]:
        return []


_pika_getter = _PikaGetter()

HookT = Callable[[Span, bytes, BasicProperties], None]


def dummy_callback(span: Span, body: bytes, properties: BasicProperties): ...


def _decorate_callback(
    callback: Callable[[Channel, Basic.Deliver, BasicProperties, bytes], Any],
    tracer: Tracer,
    task_name: str,
    consume_hook: HookT = dummy_callback,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> Callable[[Channel, Basic.Deliver, BasicProperties, bytes], Any]:
    def decorated_callback(
        channel: Channel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> Any:
        if not properties:
            properties = BasicProperties(headers={})
        if properties.headers is None:
            properties.headers = {}
        ctx = propagate.extract(properties.headers, getter=_pika_getter)
        if not ctx:
            ctx = context.get_current()
        token = context.attach(ctx)
        span = _get_span(
            tracer,
            channel,
            properties,
            destination=(method.exchange if method.exchange else method.routing_key),
            span_kind=SpanKind.CONSUMER,
            task_name=task_name,
            operation=MessagingOperationValues.RECEIVE,
            sem_conv_opt_in_mode=sem_conv_opt_in_mode,
            destination_name=_get_destination_name(method.exchange, method.routing_key),
            operation_type=messaging_attributes.MessagingOperationTypeValues.PROCESS,
        )
        try:
            with trace.use_span(span, end_on_exit=True):
                try:
                    consume_hook(span, body, properties)
                except Exception as hook_exception:  # pylint: disable=W0703
                    _LOG.exception(hook_exception)
                retval = callback(channel, method, properties, body)
        finally:
            if token:
                context.detach(token)
        return retval

    return decorated_callback


def _decorate_basic_publish(
    original_function: Callable[[str, str, bytes, BasicProperties, bool], Any],
    channel: Channel,
    tracer: Tracer,
    publish_hook: HookT = dummy_callback,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> Callable[..., Any]:
    def decorated_function(
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: BasicProperties | None = None,
        mandatory: bool = False,
    ) -> Any:
        if not properties:
            properties = BasicProperties(headers={})
        if properties.headers is None:
            properties.headers = {}
        span = _get_span(
            tracer,
            channel,
            properties,
            destination=exchange if exchange else routing_key,
            span_kind=SpanKind.PRODUCER,
            task_name="(temporary)",
            operation=None,
            sem_conv_opt_in_mode=sem_conv_opt_in_mode,
            destination_name=_get_destination_name(exchange, routing_key),
            operation_type=messaging_attributes.MessagingOperationTypeValues.SEND,
        )
        if not span:
            return original_function(exchange, routing_key, body, properties, mandatory)
        with trace.use_span(span, end_on_exit=True):
            propagate.inject(properties.headers)
            try:
                publish_hook(span, body, properties)
            except Exception as hook_exception:  # pylint: disable=W0703
                _LOG.exception(hook_exception)
            retval = original_function(exchange, routing_key, body, properties, mandatory)
        return retval

    return decorated_function


def _get_span(
    tracer: Tracer,
    channel: Channel | None,
    properties: BasicProperties,
    task_name: str,
    destination: str,
    span_kind: SpanKind,
    operation: MessagingOperationValues | None = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    destination_name: str | None = None,
    operation_type: messaging_attributes.MessagingOperationTypeValues | None = None,
) -> Span | None:
    if not is_instrumentation_enabled():
        return None
    task_name = properties.type if properties.type else task_name
    span = tracer.start_span(
        name=_generate_span_name(
            destination_name if _report_new(sem_conv_opt_in_mode) and destination_name is not None else destination,
            operation,
            sem_conv_opt_in_mode,
            operation_type,
        ),
        kind=(
            SpanKind.CLIENT
            if _report_new(sem_conv_opt_in_mode)
            and operation_type == messaging_attributes.MessagingOperationTypeValues.RECEIVE
            else span_kind
        ),
    )
    if span.is_recording():
        _enrich_span(
            span,
            channel,
            properties,
            destination,
            operation,
            sem_conv_opt_in_mode,
            destination_name,
            operation_type,
        )
    return span


def _generate_span_name(
    task_name: str,
    operation: MessagingOperationValues | None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    operation_type: messaging_attributes.MessagingOperationTypeValues | None = None,
) -> str:
    if _report_new(sem_conv_opt_in_mode):
        return f"{_get_operation_name(operation, operation_type)} {task_name}"
    if not operation:
        return f"{task_name} send"
    return f"{task_name} {operation.value}"


def _get_destination_name(exchange: str, routing_key: str) -> str:
    if exchange and routing_key:
        return f"{exchange}:{routing_key}"
    return exchange or routing_key or "amq.default"


def _get_operation_name(
    operation: MessagingOperationValues | None,
    operation_type: messaging_attributes.MessagingOperationTypeValues | None,
) -> str:
    if operation is None:
        return MessagingOperationValues.PUBLISH.value
    return operation_type.value if operation_type is not None else operation.value


def _enrich_span(
    span: Span,
    channel: Channel | None,
    properties: BasicProperties,
    task_destination: str,
    operation: MessagingOperationValues | None = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    destination_name: str | None = None,
    operation_type: messaging_attributes.MessagingOperationTypeValues | None = None,
) -> None:
    attributes: dict[str, AttributeValue] = {
        messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.RABBITMQ.value,
    }
    if properties.message_id:
        attributes[messaging_attributes.MESSAGING_MESSAGE_ID] = properties.message_id

    if _report_old(sem_conv_opt_in_mode):
        _set_messaging_destination(attributes, task_destination, _StabilityMode.DEFAULT)
        # The legacy instrumentation also recorded an empty destination.
        if not task_destination:
            attributes[SpanAttributes.MESSAGING_DESTINATION] = task_destination
        if operation is None:
            _set_messaging_temp_destination(attributes, True, _StabilityMode.DEFAULT)
        else:
            _set_messaging_operation(attributes, operation.value, _StabilityMode.DEFAULT)

    if _report_new(sem_conv_opt_in_mode):
        _set_messaging_destination(
            attributes,
            destination_name if destination_name is not None else task_destination,
            _StabilityMode.MESSAGING,
        )
        operation_name = _get_operation_name(operation, operation_type)
        _set_messaging_operation(attributes, operation_name, _StabilityMode.MESSAGING)
        attributes[messaging_attributes.MESSAGING_OPERATION_NAME] = operation_name
        # Publishing alone does not tell us whether a destination is temporary.

    if properties.correlation_id:
        _set_messaging_conversation_id(attributes, properties.correlation_id, sem_conv_opt_in_mode)

    for key, value in attributes.items():
        span.set_attribute(key, value)

    if channel is None:
        return

    connection = channel.connection
    params = connection.params if hasattr(connection, "params") else connection._impl.params

    if _report_old(sem_conv_opt_in_mode):
        span.set_attribute(SpanAttributes.NET_PEER_NAME, params.host)
        span.set_attribute(SpanAttributes.NET_PEER_PORT, params.port)

    if _report_new(sem_conv_opt_in_mode):
        span.set_attribute(server_attributes.SERVER_ADDRESS, params.host)
        span.set_attribute(server_attributes.SERVER_PORT, params.port)


# pylint:disable=abstract-method
class ReadyMessagesDequeProxy(ObjectProxy):
    def __init__(
        self,
        wrapped,
        queue_consumer_generator: _QueueConsumerGeneratorInfo,
        tracer: Tracer | None,
        consume_hook: HookT = dummy_callback,
        sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
    ):
        super().__init__(wrapped)
        self._self_active_token = None
        self._self_tracer = tracer
        self._self_consume_hook = consume_hook
        self._self_sem_conv_opt_in_mode = sem_conv_opt_in_mode
        self._self_queue_consumer_generator = queue_consumer_generator

    def popleft(self, *args, **kwargs):
        try:
            if self._self_active_token:
                context.detach(self._self_active_token)
        except Exception as inst_exception:  # pylint: disable=W0703
            _LOG.exception(inst_exception)

        evt = self.__wrapped__.popleft(*args, **kwargs)  # pylint:disable=no-member

        try:
            if isinstance(evt, _ConsumerDeliveryEvt):
                method = evt.method
                properties = evt.properties
                if not properties:
                    properties = BasicProperties(headers={})
                if properties.headers is None:
                    properties.headers = {}
                ctx = propagate.extract(properties.headers, getter=_pika_getter)
                if not ctx:
                    ctx = context.get_current()
                message_ctx_token = context.attach(ctx)
                span = _get_span(
                    self._self_tracer,
                    None,
                    properties,
                    destination=(method.exchange if method.exchange else method.routing_key),
                    span_kind=SpanKind.CONSUMER,
                    task_name=self._self_queue_consumer_generator.consumer_tag,
                    operation=MessagingOperationValues.RECEIVE,
                    sem_conv_opt_in_mode=self._self_sem_conv_opt_in_mode,
                    destination_name=_get_destination_name(method.exchange, method.routing_key),
                    operation_type=messaging_attributes.MessagingOperationTypeValues.RECEIVE,
                )
                try:
                    if message_ctx_token:
                        context.detach(message_ctx_token)
                    self._self_active_token = context.attach(trace.set_span_in_context(span))
                    self._self_consume_hook(span, evt.body, properties)
                except Exception as hook_exception:  # pylint: disable=W0703
                    _LOG.exception(hook_exception)
                finally:
                    span.end()
        except Exception as inst_exception:  # pylint: disable=W0703
            _LOG.exception(inst_exception)

        return evt
