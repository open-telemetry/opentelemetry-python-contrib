import json
from logging import getLogger
from typing import Callable, List

from google.cloud.pubsub_v1.subscriber.message import Message
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer

from opentelemetry import propagate, trace

_LOG = getLogger(__name__)


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

    _publish_not_attributes_kwarg_keys = {"topic", "data", "ordering_key", "retry", "timeout"}

    @staticmethod
    def extract_publish_metadata(args, kwargs):
        """extract data from `publish` method arguments in PublisherClient class"""
        return {k: v for k, v in kwargs.item() if k not in PubsubPropertiesExtractor._publish_not_attributes_kwarg_keys}

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


def _wrap_publish(tracer: Tracer) -> Callable:
    def _traced_send(func, instance, args, kwargs):
        headers = PubsubPropertiesExtractor.extract_publish_metadata(args, kwargs)
        kwargs["headers"] = headers

        topic = PubsubPropertiesExtractor.extract_publish_topic(args, kwargs)
        span_name = _get_span_name("send", topic)
        with tracer.start_as_current_span(
                span_name, kind=trace.SpanKind.PRODUCER
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "pubsub")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, topic)
            propagate.inject(
                headers,
                context=trace.set_span_in_context(span),
            )

            return func(*args, **kwargs)

    return _traced_send


def _wrap_subscribe(
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
                if span.is_recording():
                    span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "pubsub")
                    span.set_attribute(SpanAttributes.MESSAGING_CONSUMER_ID, subscription)

                if callable(callback):
                    callback(message)

        kwargs["subscription"] = subscription
        kwargs["callback"] = _traced_callback

        return func(subscription, callback, *args[2:], **kwargs)

    return _traced_subscribe
