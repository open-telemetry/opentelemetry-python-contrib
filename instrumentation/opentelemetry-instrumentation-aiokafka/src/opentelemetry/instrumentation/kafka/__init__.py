# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Instrument aiokafka to report instrumentation-aiokafka produced and consumed messages

Usage
-----

..code:: python

    from opentelemetry.instrumentation.aiokafka import AIOKafkaKafkaInstrumentor
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    # Instrument aiokafka
    AIOKafkaKafkaInstrumentor().instrument()

    # report a span of type producer with the default settings
    producer = AIOKafkaProducer(bootstrap_servers=['localhost:9092'])
    producer.send('my-topic', b'raw_bytes')

    # report a span of type consumer with the default settings
    consumer = AIOKafkaConsumer('my-topic', group_id='my-group', bootstrap_servers=['localhost:9092'])
    async for message in consumer:
    # process message

The _instrument() method accepts the following keyword args:
tracer_provider (TracerProvider) - an optional tracer provider
produce_hook (Callable) - a function with extra user-defined logic to be performed before sending the message
this function signature is:
def produce_hook(span: Span, args, kwargs)
consume_hook (Callable) - a function with extra user-defined logic to be performed after consuming a message
this function signature is:
def consume_hook(span: Span, record: ConsumerRecord, args, kwargs)
for example:

.. code: python
    from opentelemetry.instrumentation.aiokafka import AIOKafkaKafkaInstrumentor
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

    def produce_hook(span, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_produce_hook", "some-value")
    def consume_hook(span, record, args, kwargs):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_consume_hook", "some-value")

    # instrument aiokafka with produce and consume hooks
    AIOKafkaKafkaInstrumentor().instrument(produce_hook=produce_hook, consume_hook=consume_hook)

    # Using aiokafka as normal now will automatically generate spans,
    # including user custom attributes added from the hooks
    producer = AIOKafkaProducer(bootstrap_servers=['localhost:9092'])
    await producer.send('my-topic', b'raw_bytes')

API
___
"""
import functools
from typing import Any, Collection

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap

from .package import _instruments
from .utils import _wrap_anext, _wrap_record_processing, _wrap_send
from .version import __version__


class AIOKafkaKafkaInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """
        Instruments the kafka module
        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``produce_hook``: a callable to be executed just before producing a message
                ``consume_hook``: a callable to be executed just after consuming a message
        """

        tracer_provider = kwargs.get("tracer_provider")
        produce_hook = kwargs.get("produce_hook")
        consume_hook = kwargs.get("consume_hook")

        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        wrap_function_wrapper(
            AIOKafkaProducer, "send", _wrap_send(tracer, produce_hook)
        )
        wrap_function_wrapper(
            AIOKafkaConsumer,
            "__anext__",
            _wrap_anext(tracer, consume_hook),
        )

    def _uninstrument(self, **kwargs):
        unwrap(AIOKafkaProducer, "send")
        unwrap(AIOKafkaConsumer, "__next__")
