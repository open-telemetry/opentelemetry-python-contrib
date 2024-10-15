import json
from logging import getLogger
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

import aiokafka
from aiokafka import ConsumerRecord

from opentelemetry import context, propagate, trace
from opentelemetry.context import Context
from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


def _extract_bootstrap_servers(
    client: aiokafka.AIOKafkaClient,
) -> Union[str, List[str]]:
    return client._bootstrap_servers


def _extract_client_id(client: aiokafka.AIOKafkaClient) -> str:
    return client._client_id


def _extract_consumer_group(
    consumer: aiokafka.AIOKafkaConsumer,
) -> Optional[str]:
    return consumer._group_id


def _extract_argument(
    key: str,
    position: int,
    default_value: Any,
    args: Tuple[Any],
    kwargs: Dict[str, Any],
) -> Any:
    if len(args) > position:
        return args[position]
    return kwargs.get(key, default_value)


def _extract_send_topic(args: Tuple[Any], kwargs: Dict[str, Any]) -> str:
    """extract topic from `send` method arguments in AIOKafkaProducer class"""
    return _extract_argument("topic", 0, "unknown", args, kwargs)


def _extract_send_value(
    args: Tuple[Any], kwargs: Dict[str, Any]
) -> Optional[Any]:
    """extract value from `send` method arguments in AIOKafkaProducer class"""
    return _extract_argument("value", 1, None, args, kwargs)


def _extract_send_key(
    args: Tuple[Any], kwargs: Dict[str, Any]
) -> Optional[Any]:
    """extract key from `send` method arguments in AIOKafkaProducer class"""
    return _extract_argument("key", 2, None, args, kwargs)


def _extract_send_headers(args: Tuple[Any], kwargs: Dict[str, Any]):
    """extract headers from `send` method arguments in AIOKafkaProducer class"""
    return _extract_argument("headers", 5, None, args, kwargs)


async def _extract_send_partition(
    instance: aiokafka.AIOKafkaProducer,
    args: Tuple[Any],
    kwargs: Dict[str, Any],
) -> Optional[int]:
    """extract partition `send` method arguments, using the `_partition` method in AIOKafkaProducer class"""
    try:
        topic = _extract_send_topic(args, kwargs)
        key = _extract_send_key(args, kwargs)
        value = _extract_send_value(args, kwargs)
        partition = _extract_argument("partition", 3, None, args, kwargs)
        key_bytes, value_bytes = instance._serialize(topic, key, value)
        valid_types = (bytes, bytearray, memoryview, type(None))
        if (
            type(key_bytes) not in valid_types
            or type(value_bytes) not in valid_types
        ):
            return None

        await instance.client._wait_on_metadata(topic)

        return instance._partition(
            topic, partition, key, value, key_bytes, value_bytes
        )
    except Exception as exception:  # pylint: disable=W0703
        _LOG.debug("Unable to extract partition: %s", exception)
        return None


ProduceHookT = Optional[Callable[[Span, Tuple, Dict], Awaitable[None]]]
ConsumeHookT = Optional[
    Callable[[Span, ConsumerRecord, Tuple, Dict], Awaitable[None]]
]

HeadersT = List[Tuple[str, Optional[bytes]]]


class AIOKafkaContextGetter(textmap.Getter[HeadersT]):
    def get(self, carrier: HeadersT, key: str) -> Optional[List[str]]:
        if carrier is None:
            return None

        for item_key, value in carrier:
            if item_key == key:
                if value is not None:
                    return [value.decode()]
        return None

    def keys(self, carrier: HeadersT) -> List[str]:
        if carrier is None:
            return []
        return [key for (key, value) in carrier]


class AIOKafkaContextSetter(textmap.Setter[HeadersT]):
    def set(
        self, carrier: HeadersT, key: Optional[str], value: Optional[str]
    ) -> None:
        if carrier is None or key is None:
            return

        if value is not None:
            carrier.append((key, value.encode()))
        else:
            carrier.append((key, value))


_aiokafka_getter = AIOKafkaContextGetter()
_aiokafka_setter = AIOKafkaContextSetter()


def _enrich_base_span(
    span: Span,
    *,
    bootstrap_servers: Union[str, List[str]],
    client_id: str,
    topic: str,
    partition: Optional[int],
    key: Optional[Any],
) -> None:
    span.set_attribute(
        messaging_attributes.MESSAGING_SYSTEM,
        messaging_attributes.MessagingSystemValues.KAFKA.value,
    )
    span.set_attribute(
        server_attributes.SERVER_ADDRESS, json.dumps(bootstrap_servers)
    )
    span.set_attribute(messaging_attributes.MESSAGING_CLIENT_ID, client_id)
    span.set_attribute(messaging_attributes.MESSAGING_DESTINATION_NAME, topic)

    if partition is not None:
        span.set_attribute(
            messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID,
            str(partition),
        )

    if key is not None:
        span.set_attribute(
            messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY, key
        )


def _enrich_send_span(
    span: Span,
    *,
    bootstrap_servers: Union[str, List[str]],
    client_id: str,
    topic: str,
    partition: Optional[int],
    key: Optional[str],
) -> None:
    if not span.is_recording():
        return

    _enrich_base_span(
        span,
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        topic=topic,
        partition=partition,
        key=key,
    )

    span.set_attribute(messaging_attributes.MESSAGING_OPERATION_NAME, "send")
    span.set_attribute(
        messaging_attributes.MESSAGING_OPERATION_TYPE,
        messaging_attributes.MessagingOperationTypeValues.PUBLISH.value,
    )


def _enrich_anext_span(
    span: Span,
    *,
    bootstrap_servers: Union[str, List[str]],
    client_id: str,
    consumer_group: Optional[str],
    topic: str,
    partition: Optional[int],
    key: Optional[str],
    offset: int,
) -> None:
    if not span.is_recording():
        return

    _enrich_base_span(
        span,
        bootstrap_servers=bootstrap_servers,
        client_id=client_id,
        topic=topic,
        partition=partition,
        key=key,
    )

    if consumer_group is not None:
        span.set_attribute(
            messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME, consumer_group
        )

    span.set_attribute(
        messaging_attributes.MESSAGING_OPERATION_NAME, "receive"
    )
    span.set_attribute(
        messaging_attributes.MESSAGING_OPERATION_TYPE,
        messaging_attributes.MessagingOperationTypeValues.RECEIVE.value,
    )

    span.set_attribute(
        messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET, offset
    )

    # https://stackoverflow.com/questions/65935155/identify-and-find-specific-message-in-kafka-topic
    # A message within Kafka is uniquely defined by its topic name, topic partition and offset.
    if partition is not None:
        span.set_attribute(
            messaging_attributes.MESSAGING_MESSAGE_ID,
            f"{topic}.{partition}.{offset}",
        )


def _get_span_name(operation: str, topic: str):
    return f"{topic} {operation}"


def _wrap_send(
    tracer: Tracer, async_produce_hook: ProduceHookT
) -> Callable[..., Awaitable[None]]:
    async def _traced_send(
        func: Callable[..., Awaitable[None]],
        instance: aiokafka.AIOKafkaProducer,
        args: Tuple[Any],
        kwargs: Dict[str, Any],
    ) -> None:
        headers = _extract_send_headers(args, kwargs)
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = _extract_send_topic(args, kwargs)
        bootstrap_servers = _extract_bootstrap_servers(instance.client)
        client_id = _extract_client_id(instance.client)
        key = _extract_send_key(args, kwargs)
        partition = await _extract_send_partition(instance, args, kwargs)
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            _enrich_send_span(
                span,
                bootstrap_servers=bootstrap_servers,
                client_id=client_id,
                topic=topic,
                partition=partition,
                key=key,
            )
            propagate.inject(
                headers,
                context=trace.set_span_in_context(span),
                setter=_aiokafka_setter,
            )
            try:
                if async_produce_hook is not None:
                    await async_produce_hook(span, args, kwargs)
            except Exception as hook_exception:  # pylint: disable=W0703
                _LOG.exception(hook_exception)

        return await func(*args, **kwargs)

    return _traced_send


async def _create_consumer_span(
    tracer: Tracer,
    async_consume_hook: ConsumeHookT,
    record: ConsumerRecord,
    extracted_context: Context,
    bootstrap_servers: Union[str, List[str]],
    client_id: str,
    consumer_group: Optional[str],
    args: Tuple[Any],
    kwargs: Dict[str, Any],
):
    span_name = _get_span_name("receive", record.topic)
    with tracer.start_as_current_span(
        span_name,
        context=extracted_context,
        kind=trace.SpanKind.CONSUMER,
    ) as span:
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
        _enrich_anext_span(
            span,
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            consumer_group=consumer_group,
            topic=record.topic,
            partition=record.partition,
            key=record.key,
            offset=record.offset,
        )
        try:
            if async_consume_hook is not None:
                await async_consume_hook(span, record, args, kwargs)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        context.detach(token)


def _wrap_getone(
    tracer: Tracer, async_consume_hook: ConsumeHookT
) -> Callable[..., Awaitable[aiokafka.ConsumerRecord]]:
    async def _traced_next(
        func: Callable[..., Awaitable[aiokafka.ConsumerRecord]],
        instance: aiokafka.AIOKafkaConsumer,
        args: Tuple[Any],
        kwargs: Dict[str, Any],
    ) -> aiokafka.ConsumerRecord:
        record = await func(*args, **kwargs)

        if record:
            bootstrap_servers = _extract_bootstrap_servers(instance._client)
            client_id = _extract_client_id(instance._client)
            consumer_group = _extract_consumer_group(instance)

            extracted_context = propagate.extract(
                record.headers, getter=_aiokafka_getter
            )
            await _create_consumer_span(
                tracer,
                async_consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                client_id,
                consumer_group,
                args,
                kwargs,
            )
        return record

    return _traced_next
