import pika
from logging import getLogger
from pika.channel import Channel
from pika.adapters import BaseConnection
from typing import Dict, Callable, Optional, Collection, Any
from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.instrumentation.pika import utils
from opentelemetry.trace import Tracer, TracerProvider
from opentelemetry.instrumentation.pika import __version__
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.instrumentation.pika.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


_LOG = getLogger(__name__)
CTX_KEY = "__otel_task_span"

FUNCTIONS_TO_UNINSTRUMENT = ["basic_publish"]


class PikaInstrumentation(BaseInstrumentor):  # type: ignore
    @staticmethod
    def _instrument_consumers(
        consumers_dict: Dict[str, Callable[..., Any]], tracer: Tracer
    ) -> Any:
        for key, callback in consumers_dict.items():

            def decorated_callback(
                channel: Channel,
                method: pika.spec.Basic.Deliver,
                properties: pika.spec.BasicProperties,
                body: bytes,
            ) -> Any:
                if not properties:
                    properties = pika.spec.BasicProperties()
                span = utils.get_span(
                    tracer,
                    channel,
                    properties,
                    task_name=key,
                    operation=MessagingOperationValues.RECEIVE,
                )
                with trace.use_span(span, end_on_exit=True):
                    inject(properties.headers)
                    retval = callback(channel, method, properties, body)
                return retval

            decorated_callback.__setattr__("_original_callback", callback)
            consumers_dict[key] = decorated_callback

    @staticmethod
    def _instrument_basic_publish(channel: Channel, tracer: Tracer) -> None:
        original_function = getattr(channel, "basic_publish")

        def decorated_function(
            exchange: str,
            routing_key: str,
            body: bytes,
            properties: pika.spec.BasicProperties = None,
            mandatory: bool = False,
        ) -> Any:
            if not properties:
                properties = pika.spec.BasicProperties()
            span = utils.get_span(
                tracer,
                channel,
                properties,
                task_name="(temporary)",
                operation=None,
            )
            with trace.use_span(span, end_on_exit=True):
                inject(properties.headers)
                retval = original_function(
                    exchange, routing_key, body, properties, mandatory
                )
            return retval

        decorated_function.__setattr__("_original_function", original_function)
        channel.__setattr__("basic_publish", decorated_function)
        channel.basic_publish = decorated_function

    @staticmethod
    def _instrument_channel_functions(
        channel: Channel, tracer: Tracer
    ) -> None:
        if hasattr(channel, "basic_publish"):
            PikaInstrumentation._instrument_basic_publish(channel, tracer)

    @staticmethod
    def _uninstrument_channel_functions(channel: Channel) -> None:
        for function_name in FUNCTIONS_TO_UNINSTRUMENT:
            if not hasattr(channel, function_name):
                continue
            function = getattr(channel, function_name)
            if hasattr(function, "_original_function"):
                channel.__setattr__(function_name, function._original_function)

    @staticmethod
    def instrument_channel(
        channel: Channel,
        tracer_provider: Optional[TracerProvider] = None,
    ) -> None:
        if not hasattr(channel, "_impl") or not isinstance(
            channel._impl, Channel
        ):
            _LOG.error("Could not find implementation for provided channel!")
            return
        tracer = trace.get_tracer(__name__, __version__, tracer_provider)
        channel.__setattr__("__opentelemetry_tracer", tracer)
        if channel._impl._consumers:
            PikaInstrumentation._instrument_consumers(
                channel._impl._consumers, tracer
            )
        PikaInstrumentation._instrument_channel_functions(channel, tracer)

    def _instrument(self, **kwargs: Dict[str, Any]) -> None:
        channel: Channel = kwargs.get("channel", None)
        if not channel or not isinstance(channel, Channel):
            return
        tracer_provider: TracerProvider = kwargs.get("tracer_provider", None)
        PikaInstrumentation.instrument_channel(channel, tracer_provider=tracer_provider)

    def _uninstrument(self, **kwargs: Dict[str, Any]) -> None:
        channel: Channel = kwargs.get("channel", None)
        if not channel or not isinstance(channel, Channel):
            return
        if not hasattr(channel, "_impl") or not isinstance(
            channel._impl, BaseConnection
        ):
            _LOG.error("Could not find implementation for provided channel!")
            return
        for key, callback in channel._impl._consumers:
            if hasattr(callback, "_original_callback"):
                channel._consumers[key] = callback._original_callback
        PikaInstrumentation._uninstrument_channel_functions(channel)

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
