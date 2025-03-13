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
Instrument karapace-python to report instrumentation-karapace produced and consumed messages

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.confluent_kafka import KarapaceInstrumentor
    from confluent_kafka import Producer, Consumer

    # Instrument kafka
    KarapaceInstrumentor().instrument()

    # report a span of type producer with the default settings
    conf1 = {'bootstrap.servers': "localhost:9092"}
    producer = Producer(conf1)
    producer.produce('my-topic',b'raw_bytes')
    conf2 = {'bootstrap.servers': "localhost:9092", 'group.id': "foo", 'auto.offset.reset': 'smallest'}
    # report a span of type consumer with the default settings
    consumer = Consumer(conf2)

    def basic_consume_loop(consumer, topics):
        try:
            consumer.subscribe(topics)
            running = True
            while running:
                msg = consumer.poll(timeout=1.0)
                if msg is None: continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition event
                        sys.stderr.write(f"{msg.topic() [{msg.partition()}] reached end at offset {msg.offset()}}")
                    elif msg.error():
                        raise KafkaException(msg.error())
                else:
                    msg_process(msg)
        finally:
            # Close down consumer to commit final offsets.
            consumer.close()

    basic_consume_loop(consumer, "my-topic")
    ---

The _instrument method accepts the following keyword args:
  tracer_provider (TracerProvider) - an optional tracer provider

  instrument_producer (Callable) - a function with extra user-defined logic to be performed before sending the message
    this function signature is:

  def instrument_producer(producer: Producer, tracer_provider=None)

    instrument_consumer (Callable) - a function with extra user-defined logic to be performed after consuming a message
        this function signature is:

  def instrument_consumer(consumer: Consumer, tracer_provider=None)
    for example:

.. code:: python

    from opentelemetry.instrumentation.confluent_kafka import KarapaceInstrumentor

    from confluent_kafka import Producer, Consumer

    inst = KarapaceInstrumentor()

    p = confluent_kafka.Producer({'bootstrap.servers': 'localhost:29092'})
    c = confluent_kafka.Consumer({
        'bootstrap.servers': 'localhost:29092',
        'group.id': 'mygroup',
        'auto.offset.reset': 'earliest'
    })

    # instrument karapace with produce and consume hooks
    p = inst.instrument_producer(p, tracer_provider)
    c = inst.instrument_consumer(c, tracer_provider=tracer_provider)

    # Using kafka as normal now will automatically generate spans,
    # including user custom attributes added from the hooks
    conf = {'bootstrap.servers': "localhost:9092"}
    p.produce('my-topic',b'raw_bytes')
    msg = c.poll()

___
"""
import cgi
import json
import logging

import re
from typing import Collection, Optional
import os
from requests import options
import sys
import os
import asyncio

sys.path += [
    os.getcwd(),
]
import karapace
import wrapt
from karapace.kafka_rest_apis import UserRestProxy
from karapace.rapu import HTTPRequest, HTTPResponse

from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import MessagingOperationValues
from opentelemetry.trace import Link, SpanKind, Tracer
from opentelemetry.trace.span import Span

from .package import _instruments
from .utils import (
    KafkaPropertiesExtractor,
    _enrich_span,
    _get_span_name,
    _kafka_getter,
    _kafka_setter,
)
from .version import __version__

logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel("DEBUG")
log = logging.getLogger(__name__)

from opentelemetry import trace


class AutoInstrumentedUserRestProxy(UserRestProxy):
    def __init__(self, config, kafka_timeout, serializer):
        super().__init__(config, kafka_timeout, serializer)
        log.debug("AutoInstrumentedUserRestProxy#__init__")

    async def publish(
        self,
        topic: str,
        partition_id: Optional[str],
        content_type: str,
        request: HTTPRequest,
    ) -> None:  # pylint: disable=keyword-arg-before-vararg,useless-super-delegation
        log.debug("AutoInstrumentedUserRestProxy#publish")

        span_name = _get_span_name("send", topic)
        result = None
        with self._tracer.start_as_current_span(name=span_name, kind=trace.SpanKind.PRODUCER) as span:
            headers = KafkaPropertiesExtractor.extract_produce_headers(request, None)
            if headers is None:
                raise NotImplementedError

            _enrich_span(
                span,
                topic,
            )  # Replace
            propagate.inject(
                headers,
                setter=_kafka_setter,
            )

            # karapace seems to use exceptions as fast return
            try:
                await super().publish(topic, partition_id, content_type, request)
            except HTTPResponse as response:
                result = response
                _enrich_span(span, topic, result.body["offsets"][0]["partition"], result.body["offsets"][0]["offset"])

        # close span
        raise result

    async def fetch(self, group_name: str, instance: str, content_type: str, *, request: HTTPRequest) -> None:
        log.debug("AutoInstrumentedUserRestProxy#_fetch")

        result = None
        with self._tracer.start_as_current_span("recv", end_on_exit=True, kind=trace.SpanKind.CONSUMER) as span:
            try:
                # karapace seems to use exceptions as fast return
                await super().fetch(
                    group_name=group_name, instance=instance, content_type=content_type, request=request
                )
            except HTTPResponse as response:
                record = response.body
                result = response
                if record:
                    links = []
                    ctx = propagate.extract(response.headers, getter=_kafka_getter)
                    if ctx:
                        for item in ctx.values():
                            if hasattr(item, "get_span_context"):
                                links.append(Link(context=item.get_span_context()))

                    span_name = _get_span_name("recv", record[0]["topic"])
                    span.update_name(span_name)
                    _enrich_span(
                        span,
                        record[0]["topic"],
                        record[0]["partition"],
                        record[0]["offset"],
                        operation=MessagingOperationValues.PROCESS,
                    )
        # close span
        raise result


class KarapaceInstrumentor(BaseInstrumentor):
    """
    An instrumentor for karapace module see `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        self._original_userrestproxy = karapace.kafka_rest_apis.UserRestProxy

        karapace.kafka_rest_apis.UserRestProxy = AutoInstrumentedUserRestProxy

        # we use the global defined tracer.
        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(__name__, __version__, tracer_provider=tracer_provider)
        self._tracer = tracer

        log.debug("KarapaceInstrumentor#_instrument")

        karapace.kafka_rest_apis.UserRestProxy._tracer = self._tracer

    def _uninstrument(self, **kwargs):
        karapace.kafka_rest_apis.UserRestProxy = self._original_userrestproxy
