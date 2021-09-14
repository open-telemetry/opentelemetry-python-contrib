from typing import Any, Callable, List, Optional

from pika.channel import Channel
from pika.spec import Basic, BasicProperties

from opentelemetry import propagate, trace
from opentelemetry.propagators.textmap import CarrierT, Getter
from opentelemetry.semconv.trace import (
    MessagingOperationValues,
    SpanAttributes,
)
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span


class PikaGetter(Getter):  # type: ignore
    def get(self, carrier: CarrierT, key: str) -> Optional[List[str]]:
        value = carrier.get(key, None)
        if value is None:
            return None
        return [value]

    def keys(self, carrier: CarrierT) -> List[str]:
        return []


pika_getter = PikaGetter()


def decorate_callback(
    callback: Callable[[Channel, Basic.Deliver, BasicProperties, bytes], Any],
    tracer: Tracer,
    task_name: str,
):
    def decorated_callback(
        channel: Channel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> Any:
        if not properties:
            properties = BasicProperties()
        span = get_span(
            tracer,
            channel,
            properties,
            task_name=task_name,
            operation=MessagingOperationValues.RECEIVE,
        )
        with trace.use_span(span, end_on_exit=True):
            propagate.inject(properties.headers)
            retval = callback(channel, method, properties, body)
        return retval

    return decorated_callback


def decorate_basic_publish(
    original_function: Callable[[str, str, bytes, BasicProperties, bool], Any],
    channel: Channel,
    tracer: Tracer,
):
    def decorated_function(
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: BasicProperties = None,
        mandatory: bool = False,
    ) -> Any:
        if not properties:
            properties = BasicProperties()
        span = get_span(
            tracer,
            channel,
            properties,
            task_name="(temporary)",
            operation=None,
        )
        with trace.use_span(span, end_on_exit=True):
            propagate.inject(properties.headers)
            retval = original_function(
                exchange, routing_key, body, properties, mandatory
            )
        return retval

    return decorated_function


def get_span(
    tracer: Tracer,
    channel: Channel,
    properties: BasicProperties,
    task_name: str,
    operation: Optional[MessagingOperationValues] = None,
) -> Span:
    if properties.headers is None:
        properties.headers = {}
    ctx = propagate.extract(properties.headers, getter=pika_getter)
    task_name = properties.type if properties.type else task_name
    span = tracer.start_span(
        context=ctx, name=generate_span_name(task_name, operation)
    )
    enrich_span(span, channel, properties, task_name, operation)
    return span


def generate_span_name(
    task_name: str, operation: Optional[MessagingOperationValues]
) -> str:
    if not operation:
        return f"{task_name} send"
    return f"{task_name} {operation.value}"


def enrich_span(
    span: Span,
    channel: Channel,
    properties: BasicProperties,
    task_destination: str,
    operation: Optional[MessagingOperationValues] = None,
) -> None:
    span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "rabbitmq")
    if operation:
        span.set_attribute(SpanAttributes.MESSAGING_OPERATION, operation.value)
    else:
        span.set_attribute(SpanAttributes.MESSAGING_TEMP_DESTINATION, True)
    span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, task_destination)
    if properties.message_id:
        span.set_attribute(
            SpanAttributes.MESSAGING_MESSAGE_ID, properties.message_id
        )
    if properties.correlation_id:
        span.set_attribute(
            SpanAttributes.MESSAGING_CONVERSATION_ID, properties.correlation_id
        )
    if not hasattr(channel.connection, "params"):
        span.set_attribute(
            SpanAttributes.NET_PEER_NAME, channel.connection._impl.params.host
        )
        span.set_attribute(
            SpanAttributes.NET_PEER_PORT, channel.connection._impl.params.port
        )
    else:
        span.set_attribute(
            SpanAttributes.NET_PEER_NAME, channel.connection.params.host
        )
        span.set_attribute(
            SpanAttributes.NET_PEER_PORT, channel.connection.params.port
        )
