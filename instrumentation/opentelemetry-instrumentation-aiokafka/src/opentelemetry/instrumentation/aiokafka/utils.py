import json
import typing
from logging import getLogger

import aiokafka  # type: ignore[import-untyped]

from opentelemetry import context, propagate, trace
from opentelemetry.context import Context
from opentelemetry.propagators import textmap
from opentelemetry.semconv.trace import (
    MessagingOperationValues,
    SpanAttributes,
)
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)

ArgsT = typing.Tuple[typing.Any]
KwargsT = typing.Dict[str, typing.Any]
CarrierT = typing.List[typing.Tuple[str, bytes]]


class AIOKafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(
        instance: aiokafka.AIOKafkaClient,
    ) -> typing.List[typing.Tuple[str, int]]:
        return [(host, port) for (host, port, _) in instance.hosts]

    @staticmethod
    def extract_client_id(instance: aiokafka.AIOKafkaClient) -> str:
        return instance._client_id

    @staticmethod
    def extract_get_group_id(
        instance: aiokafka.AIOKafkaConsumer,
    ) -> typing.Optional[str]:
        return instance._group_id

    @staticmethod
    def _extract_argument(
        key: str,
        position: int,
        default_value: typing.Any,
        args: ArgsT,
        kwargs: KwargsT,
    ) -> typing.Any:
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_send_topic(args: ArgsT, kwargs: KwargsT) -> str:
        """extract topic from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "topic", 0, "unknown", args, kwargs
        )

    @staticmethod
    def extract_send_value(
        args: ArgsT, kwargs: KwargsT
    ) -> typing.Optional[typing.Any]:
        """extract value from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "value", 1, None, args, kwargs
        )

    @staticmethod
    def extract_send_key(
        args: ArgsT, kwargs: KwargsT
    ) -> typing.Optional[typing.Any]:
        """extract key from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "key", 2, None, args, kwargs
        )

    @staticmethod
    def extract_send_headers(
        args: ArgsT, kwargs: KwargsT
    ) -> typing.Optional[CarrierT]:
        """extract headers from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "headers", 5, None, args, kwargs
        )

    @staticmethod
    def extract_send_partition(
        instance: aiokafka.AIOKafkaProducer, args: ArgsT, kwargs: KwargsT
    ) -> typing.Optional[int]:
        """extract partition `send` method arguments, using the `_partition` method in AIOKafkaProducer class"""
        try:
            topic = AIOKafkaPropertiesExtractor.extract_send_topic(
                args, kwargs
            )
            key = AIOKafkaPropertiesExtractor.extract_send_key(args, kwargs)
            value = AIOKafkaPropertiesExtractor.extract_send_value(
                args, kwargs
            )
            partition = AIOKafkaPropertiesExtractor._extract_argument(
                "partition", 4, None, args, kwargs
            )
            key_bytes, value_bytes = instance._serialize(topic, key, value)
            valid_types = (bytes, bytearray, memoryview, type(None))
            if (
                type(key_bytes) not in valid_types
                or type(value_bytes) not in valid_types
            ):
                return None

            return instance._partition(
                topic, partition, key, value, key_bytes, value_bytes
            )
        except Exception as exception:  # pylint: disable=W0703
            _LOG.debug("Unable to extract partition: %s", exception)
            return None


ProduceHookT = typing.Optional[typing.Callable[[Span, ArgsT, KwargsT], None]]
ConsumeHookT = typing.Optional[
    typing.Callable[[Span, aiokafka.ConsumerRecord, ArgsT, KwargsT], None]
]


class AIOKafkaContextGetter(textmap.Getter[CarrierT]):
    def get(
        self, carrier: CarrierT, key: str
    ) -> typing.Optional[typing.List[str]]:
        if carrier is None:
            return None

        for item_key, value in carrier:
            if item_key == key and value is not None:
                return [value.decode()]
        return None

    def keys(self, carrier: CarrierT) -> typing.List[str]:
        if carrier is None:
            return []
        return [key for (key, value) in carrier]


class AIOKafkaContextSetter(textmap.Setter[CarrierT]):
    def set(self, carrier: CarrierT, key: str, value: str) -> None:
        if carrier is None or key is None:
            return

        if value:
            carrier.append((key, value.encode()))
        else:
            carrier.append((key, b""))


_kafka_getter: AIOKafkaContextGetter = AIOKafkaContextGetter()
_kafka_setter: AIOKafkaContextSetter = AIOKafkaContextSetter()


def _enrich_span(
    span: Span,
    bootstrap_servers: typing.List[typing.Tuple[str, int]],
    group_id: typing.Optional[str],
    client_id: str,
    topic: str,
    key: typing.Optional[str],
    offset: typing.Optional[int],
    partition: typing.Optional[int],
    operation: MessagingOperationValues,
) -> None:
    if not span.is_recording():
        return

    span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "kafka")
    span.set_attribute(
        SpanAttributes.MESSAGING_URL, json.dumps(bootstrap_servers)
    )
    span.set_attribute(SpanAttributes.MESSAGING_CLIENT_ID, client_id)

    if group_id is not None:
        span.set_attribute(
            SpanAttributes.MESSAGING_KAFKA_CONSUMER_GROUP, group_id
        )

    span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, topic)
    span.set_attribute(SpanAttributes.MESSAGING_OPERATION, operation.value)

    if partition is not None:
        span.set_attribute(
            SpanAttributes.MESSAGING_KAFKA_DESTINATION_PARTITION, partition
        )

    if key is not None:
        span.set_attribute(SpanAttributes.MESSAGING_KAFKA_MESSAGE_KEY, key)

    if offset is not None:
        span.set_attribute(
            SpanAttributes.MESSAGING_KAFKA_MESSAGE_OFFSET, offset
        )


def _get_span_name(operation: str, topic: str) -> str:
    return f"{topic} {operation}"


def _wrap_send(tracer: Tracer, produce_hook: ProduceHookT) -> typing.Callable:
    async def _traced_send(
        func: typing.Callable[..., typing.Awaitable[None]],
        instance: aiokafka.AIOKafkaProducer,
        args: ArgsT,
        kwargs: KwargsT,
    ) -> None:
        headers = AIOKafkaPropertiesExtractor.extract_send_headers(
            args, kwargs
        )
        if headers is None:
            headers = []
            kwargs["headers"] = headers

        topic = AIOKafkaPropertiesExtractor.extract_send_topic(args, kwargs)
        bootstrap_servers = (
            AIOKafkaPropertiesExtractor.extract_bootstrap_servers(
                instance.client
            )
        )
        client_id = AIOKafkaPropertiesExtractor.extract_client_id(
            instance.client
        )
        partition = AIOKafkaPropertiesExtractor.extract_send_partition(
            instance, args, kwargs
        )
        key = AIOKafkaPropertiesExtractor.extract_send_key(args, kwargs)
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            _enrich_span(
                span=span,
                bootstrap_servers=bootstrap_servers,
                group_id=None,
                client_id=client_id,
                topic=topic,
                key=key,
                offset=None,
                partition=partition,
                operation=MessagingOperationValues.PUBLISH,
            )
            propagate.inject(
                headers,
                context=trace.set_span_in_context(span),
                setter=_kafka_setter,
            )
            try:
                if callable(produce_hook):
                    produce_hook(span, args, kwargs)
            except Exception as hook_exception:  # pylint: disable=W0703
                _LOG.exception(hook_exception)

        return await func(*args, **kwargs)

    return _traced_send


def _create_consumer_span(
    tracer: Tracer,
    consume_hook: ConsumeHookT,
    record: aiokafka.ConsumerRecord,
    extracted_context: Context,
    bootstrap_servers: typing.List[typing.Tuple[str, int]],
    group_id: typing.Optional[str],
    client_id: str,
    args: ArgsT,
    kwargs: KwargsT,
) -> None:
    span_name = _get_span_name("receive", record.topic)
    with tracer.start_as_current_span(
        span_name,
        context=extracted_context,
        kind=trace.SpanKind.CONSUMER,
    ) as span:
        new_context = trace.set_span_in_context(span, extracted_context)
        token = context.attach(new_context)
        _enrich_span(
            span=span,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
            topic=record.topic,
            key=record.key,
            offset=record.offset,
            partition=record.partition,
            operation=MessagingOperationValues.RECEIVE,
        )
        try:
            if callable(consume_hook):
                consume_hook(span, record, args, kwargs)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        context.detach(token)


def _wrap_getone(
    tracer: Tracer,
    consume_hook: ConsumeHookT,
) -> typing.Callable:
    async def _traced_getone(
        func: typing.Callable[..., typing.Awaitable[aiokafka.ConsumerRecord]],
        instance: aiokafka.AIOKafkaConsumer,
        args: ArgsT,
        kwargs: KwargsT,
    ) -> aiokafka.ConsumerRecord:
        record = await func(*args, **kwargs)

        if record:
            bootstrap_servers = (
                AIOKafkaPropertiesExtractor.extract_bootstrap_servers(
                    instance._client
                )
            )
            group_id = AIOKafkaPropertiesExtractor.extract_get_group_id(
                instance
            )
            client_id = AIOKafkaPropertiesExtractor.extract_client_id(
                instance._client
            )

            extracted_context = propagate.extract(
                record.headers, getter=_kafka_getter
            )
            _create_consumer_span(
                tracer,
                consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                group_id,
                client_id,
                args,
                kwargs,
            )
        return record

    return _traced_getone
