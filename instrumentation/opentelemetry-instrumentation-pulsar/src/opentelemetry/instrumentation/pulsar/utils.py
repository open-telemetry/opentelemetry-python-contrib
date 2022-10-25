from typing import Optional

import pulsar
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    MessagingOperationValues,
    SpanAttributes,
)


def _enrich_span(
        span,
        topic,
        operation: Optional[MessagingOperationValues] = None,
        partition_key=None,
        **_kwargs
):
    if not span.is_recording():
        return

    span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "pulsar")
    span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)

    if partition_key:
        span.set_attribute(SpanAttributes.MESSAGING_KAFKA_MESSAGE_KEY, partition_key)

    span.set_attribute(
        SpanAttributes.MESSAGING_DESTINATION_KIND,
        MessagingDestinationKindValues.QUEUE.value,
    )

    if operation:
        span.set_attribute(SpanAttributes.MESSAGING_OPERATION, operation.value)
    else:
        span.set_attribute(SpanAttributes.MESSAGING_TEMP_DESTINATION, True)


def _enrich_span_with_message(span, message: pulsar.Message):
    _enrich_span_with_message_id(span, message.message_id())


def _enrich_span_with_message_id(span, message: pulsar.MessageId):
    if not span.is_recording():
        return

    span.set_attribute(
        SpanAttributes.MESSAGING_MESSAGE_ID,
        message.entry_id(),
    )

    span.set_attribute(SpanAttributes.MESSAGING_KAFKA_PARTITION, message.partition())


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"
