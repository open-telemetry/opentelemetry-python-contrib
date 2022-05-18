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
from typing import Collection

import aio_pika

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor

from .instrumented_exchange import (
    InstrumentedExchange,
    RobustInstrumentedExchange,
)
from .instrumented_queue import InstrumentedQueue, RobustInstrumentedQueue
from .package import _instruments
from .span_builder import SpanBuilder


class AioPikaInstrumentor(BaseInstrumentor):
    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider", None)
        SpanBuilder.TRACER_PROVIDER = tracer_provider
        aio_pika.Channel.EXCHANGE_CLASS = InstrumentedExchange
        aio_pika.Channel.QUEUE_CLASS = InstrumentedQueue
        aio_pika.RobustChannel.EXCHANGE_CLASS = RobustInstrumentedExchange
        aio_pika.RobustChannel.QUEUE_CLASS = RobustInstrumentedQueue

    def _uninstrument(self, **kwargs):
        SpanBuilder.TRACER_PROVIDER = None
        aio_pika.Channel.EXCHANGE_CLASS = aio_pika.Exchange
        aio_pika.Channel.QUEUE_CLASS = aio_pika.Queue
        aio_pika.RobustChannel.EXCHANGE_CLASS = aio_pika.RobustExchange
        aio_pika.RobustChannel.QUEUE_CLASS = aio_pika.RobustQueue

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments
