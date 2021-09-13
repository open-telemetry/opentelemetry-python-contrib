from pika.channel import Channel
from typing import Optional, List
from pika.spec import BasicProperties
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span
from opentelemetry.propagate import extract
from opentelemetry.propagators.textmap import Getter, CarrierT
from opentelemetry.semconv.trace import (
    SpanAttributes,
    MessagingOperationValues,
)


class PikaGetter(Getter):  # type: ignore
    def get(self, carrier: CarrierT, key: str) -> Optional[List[str]]:
        value = carrier.get(key, None)
        if value is None:
            return None
        return [value]

    def keys(self, carrier: CarrierT) -> List[str]:
        return []


pika_getter = PikaGetter()


def get_span(
    tracer: Tracer,
    channel: Channel,
    properties: BasicProperties,
    task_name: str,
    operation: Optional[MessagingOperationValues],
) -> Span:
    if properties.headers is None:
        properties.headers = {}
    ctx = extract(properties.headers, getter=pika_getter)
    task_name = properties.type if properties.type else task_name
    span = tracer.start_span(
        context=ctx, name=generate_span_name(task_name, operation)
    )
    enrich_span(span, channel, properties, task_name, operation)
    return span


def generate_span_name(
    task_name: str, operation: MessagingOperationValues
) -> str:
    if not operation:
        return f"{task_name} send"
    return f"{task_name} {operation.value}"


def enrich_span(
    span: Span,
    channel: Channel,
    properties: BasicProperties,
    task_destination: str,
    operation: Optional[MessagingOperationValues],
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
