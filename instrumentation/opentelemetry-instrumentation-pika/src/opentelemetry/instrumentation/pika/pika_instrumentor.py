import pika
from logging import getLogger
from opentelemetry import trace
from typing import Dict, Callable
from typing import Collection, Any
from pika.adapters import BaseConnection
from opentelemetry.propagate import inject
from opentelemetry.instrumentation.pika import utils
from opentelemetry.trace import Tracer, TracerProvider
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.instrumentation.pika.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


_LOG = getLogger(__name__)
CTX_KEY = "__otel_task_span"


class PikaInstrumentation(BaseInstrumentor):
    @staticmethod
    def _instrument_consumers(
        consumers_dict: Dict[str, Callable[..., Any]], tracer: Tracer
    ) -> Any:
        for key, callback in consumers_dict.items():

            def decorated_callback(
                channel: pika.channel.Channel,
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
    def _instrument_publish(channel: Any, tracer: Tracer) -> None:
        original_basic_publish = channel.basic_publish

        def decorated_basic_publish(
            exchange, routing_key, body, properties=None, mandatory=False
        ):
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
                retval = original_basic_publish(
                    exchange, routing_key, body, properties, mandatory
                )
            return retval

        decorated_basic_publish.__setattr__(
            "_original_function", original_basic_publish
        )
        channel.basic_publish = decorated_basic_publish

    @staticmethod
    def instrument_channel(
        channel: Any, tracer_provider: TracerProvider
    ) -> None:
        if not hasattr(channel, "_impl") or not isinstance(
            channel._impl, pika.channel.Channel
        ):
            _LOG.error("Could not find implementation for provided channel!")
            return
        tracer = trace.get_tracer(__name__, pika.__version__, tracer_provider)
        if channel._impl._consumers:
            PikaInstrumentation._instrument_consumers(
                channel._impl._consumers, tracer
            )
        PikaInstrumentation._instrument_publish(channel, tracer)

    def _uninstrument(self, connection: Any, **kwargs: Dict[str, Any]) -> None:
        if not hasattr(connection, "_impl") or not isinstance(
            connection._impl, BaseConnection
        ):
            _LOG.error("Could not find implementation for provided channel!")
            return
        for key, callback in connection._impl._consumers:
            if hasattr(callback, "_original_callback"):
                connection._consumers[key] = callback._original_callback
        if hasattr(connection.basic_publish, "_original_function"):
            connection.basic_publish = (
                connection.basic_publish._original_function
            )

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
