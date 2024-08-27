import json
from logging import getLogger
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

import aiokafka
from aiokafka import ConsumerRecord

from opentelemetry import context, propagate, trace
from opentelemetry.context import Context
from opentelemetry.propagators import textmap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.trace.span import Span

_LOG = getLogger(__name__)


class AIOKafkaPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(
        client: aiokafka.AIOKafkaClient,
    ) -> Union[str, List[str]]:
        return client._bootstrap_servers

    @staticmethod
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

    @staticmethod
    def extract_send_topic(args: Tuple[Any], kwargs: Dict[str, Any]) -> str:
        """extract topic from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "topic", 0, "unknown", args, kwargs
        )

    @staticmethod
    def extract_send_value(
        args: Tuple[Any], kwargs: Dict[str, Any]
    ) -> Optional[Any]:
        """extract value from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "value", 1, None, args, kwargs
        )

    @staticmethod
    def extract_send_key(
        args: Tuple[Any], kwargs: Dict[str, Any]
    ) -> Optional[Any]:
        """extract key from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "key", 2, None, args, kwargs
        )

    @staticmethod
    def extract_send_headers(args: Tuple[Any], kwargs: Dict[str, Any]):
        """extract headers from `send` method arguments in AIOKafkaProducer class"""
        return AIOKafkaPropertiesExtractor._extract_argument(
            "headers", 5, None, args, kwargs
        )

    @staticmethod
    async def extract_send_partition(
        instance: aiokafka.AIOKafkaProducer,
        args: Tuple[Any],
        kwargs: Dict[str, Any],
    ) -> Optional[int]:
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
                "partition", 3, None, args, kwargs
            )
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


def _enrich_span(
    span: Span,
    bootstrap_servers: Union[str, List[str]],
    topic: str,
    partition: Optional[int],
) -> None:
    if not span.is_recording():
        return

    span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "kafka")
    span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)

    if partition is not None:
        span.set_attribute(SpanAttributes.MESSAGING_KAFKA_PARTITION, partition)

    span.set_attribute(
        SpanAttributes.MESSAGING_URL, json.dumps(bootstrap_servers)
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
        partition = await AIOKafkaPropertiesExtractor.extract_send_partition(
            instance, args, kwargs
        )
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            _enrich_span(span, bootstrap_servers, topic, partition)
            propagate.inject(
                headers,
                context=trace.set_span_in_context(span),
                setter=_aiokafka_setter,
            )
            try:
                if callable(async_produce_hook):
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
        _enrich_span(span, bootstrap_servers, record.topic, record.partition)
        try:
            if callable(async_consume_hook):
                await async_consume_hook(span, record, args, kwargs)
        except Exception as hook_exception:  # pylint: disable=W0703
            _LOG.exception(hook_exception)
        context.detach(token)


def _wrap_anext(
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
            bootstrap_servers = (
                AIOKafkaPropertiesExtractor.extract_bootstrap_servers(
                    instance._client
                )
            )

            extracted_context = propagate.extract(
                record.headers, getter=_aiokafka_getter
            )
            await _create_consumer_span(
                tracer,
                async_consume_hook,
                record,
                extracted_context,
                bootstrap_servers,
                args,
                kwargs,
            )
        return record

    return _traced_next
