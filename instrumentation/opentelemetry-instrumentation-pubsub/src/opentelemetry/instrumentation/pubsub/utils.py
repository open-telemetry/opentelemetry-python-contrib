import json
from logging import getLogger
from typing import Callable, List

from google.cloud.pubsub_v1.subscriber.message import Message
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer

from opentelemetry import propagate, trace

_LOG = getLogger(__name__)
_OTEL_SPAN_ATTRIBUTE = "__otel_span"


class PubsubPropertiesExtractor:
    @staticmethod
    def extract_bootstrap_servers(instance):
        return instance.config.get("bootstrap_servers")

    @staticmethod
    def _extract_argument(key, position, default_value, args, kwargs):
        if len(args) > position:
            return args[position]
        return kwargs.get(key, default_value)

    @staticmethod
    def extract_publish_topic(args, kwargs):
        """extract topic from `publish` method arguments in PublisherClient class"""
        return PubsubPropertiesExtractor._extract_argument(
            "topic", 0, "unknown", args, kwargs
        )

    @staticmethod
    def extract_publish_data(args, kwargs):
        """extract data from `publish` method arguments in PublisherClient class"""
        return PubsubPropertiesExtractor._extract_argument(
            "data", 1, None, args, kwargs
        )

    @staticmethod
    def extract_subscribe_subscription(args, kwargs):
        """extract subscription from `subscribe` method arguments in SubscriberClient class"""
        return PubsubPropertiesExtractor._extract_argument(
            "subscription", 0, "unknown", args, kwargs
        )

    @staticmethod
    def extract_subscribe_callback(args, kwargs):
        """extract subscription from `subscribe` method arguments in SubscriberClient class"""
        return PubsubPropertiesExtractor._extract_argument(
            "callback", 1, None, args, kwargs
        )


def _get_span_name(operation: str, subject: str):
    return f"{operation}: {subject}"


def wrap_publish(tracer: Tracer) -> Callable:
    def _traced_send(func, instance, args, kwargs):
        topic = PubsubPropertiesExtractor.extract_publish_topic(args, kwargs)
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
                span_name, kind=trace.SpanKind.PRODUCER, end_on_exit=False
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "pubsub")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)
            propagate.inject(
                kwargs,
                context=trace.set_span_in_context(span),
            )

            def future_done_callback(f):
                try:
                    with trace.use_span(span, end_on_exit=True):
                        span.set_attribute(SpanAttributes.MESSAGING_MESSAGE_ID, f.result())
                except Exception:
                    pass

            future = func(*args, **kwargs)
            future.add_done_callback(future_done_callback)
            return future

    return _traced_send


def wrap_subscribe(
        tracer: Tracer,
) -> Callable:
    def _traced_subscribe(func, instance, args, kwargs):
        subscription = PubsubPropertiesExtractor.extract_subscribe_subscription(args, kwargs)
        callback = PubsubPropertiesExtractor.extract_subscribe_callback(args, kwargs)
        span_name = _get_span_name("subscribe", subscription)

        def _traced_callback(message: Message):
            extracted_context = propagate.extract(message.attributes)
            with tracer.start_as_current_span(
                    span_name, kind=trace.SpanKind.CONSUMER, context=extracted_context
            ) as span:
                try:
                    setattr(message, _OTEL_SPAN_ATTRIBUTE, span)
                except Exception as e:
                    getLogger().warning(f"Cannot set 'Message.{_OTEL_SPAN_ATTRIBUTE}': {e}")
                if span.is_recording():
                    span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "pubsub")
                    span.set_attribute(SpanAttributes.MESSAGING_CONSUMER_ID, subscription)

                try:
                    if callable(callback):
                        callback(message)
                finally:
                    if hasattr(message, _OTEL_SPAN_ATTRIBUTE):
                        delattr(message, _OTEL_SPAN_ATTRIBUTE)

        for key in {"subscription", "callback"}:
            if key in kwargs:
                del kwargs[key]

        return func(subscription, _traced_callback, *args[2:], **kwargs)

    return _traced_subscribe

def set_attributes(
        attributes: dict
) -> Callable:
    def _traced(func, instance, args, kwargs):
        span = getattr(instance, _OTEL_SPAN_ATTRIBUTE, trace.INVALID_SPAN)
        if span.is_recording():
            span.set_attributes(attributes)

        return func(*args, **kwargs)

    return _traced
