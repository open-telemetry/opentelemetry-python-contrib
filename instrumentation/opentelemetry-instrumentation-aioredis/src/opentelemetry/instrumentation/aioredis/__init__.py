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
#
"""
Instrument `aioredis`_ to report Redis queries.

There are two options for instrumenting code. The first option is to use the
``opentelemetry-instrumentation`` executable which will automatically
instrument your Redis client. The second is to programmatically enable
instrumentation via the following code:

.. _aioredis: https://pypi.org/project/aioredis/

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.aioredis import AioRedisInstrumentor
    import aioredis


    # Instrument redis
    AioRedisInstrumentor().instrument()

    # This will report a span with the default settings
    client = redis.StrictRedis(host="localhost", port=6379)
    client.get("my-key")

API
---
"""

from typing import Collection

import aioredis
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.aioredis.package import _instruments
from opentelemetry.instrumentation.aioredis.util import (
    _format_command_args,
)
from opentelemetry.instrumentation.aioredis.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import SpanAttributes, NetTransportValues, DbSystemValues

_DEFAULT_SERVICE = "redis"

async def traced_execute(func, instance: aioredis.Redis, args, kwargs):
    tracer = getattr(aioredis, "_opentelemetry_tracer")
    query = _format_command_args(args)
    name: str = ""
    if len(args) > 0 and args[0]:
        name = args[0].decode("utf-8")
    else:
        name = str(instance.db)
    with tracer.start_as_current_span(name, kind=trace.SpanKind.CLIENT) as span:
        if span.is_recording():
            span.set_attributes(
                {
                    SpanAttributes.DB_SYSTEM: DbSystemValues.REDIS.value,
                    SpanAttributes.DB_STATEMENT: query,
                    SpanAttributes.DB_NAME: instance.db,
                    SpanAttributes.DB_REDIS_DATABASE_INDEX: instance.db,
                }
            )
            span.set_attribute("db.redis.args_length", len(args))
            if instance.address:
                span.set_attributes(
                    {
                        SpanAttributes.NET_PEER_NAME: instance.address[0],
                        SpanAttributes.NET_PEER_PORT: instance.address[1],
                        SpanAttributes.NET_TRANSPORT: NetTransportValues.IP_TCP.value,
                    }
                )
        return await func(*args, **kwargs)


class AioRedisInstrumentor(BaseInstrumentor):
    """An instrumentor for aioredis
    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        setattr(
            aioredis,
            "_opentelemetry_tracer",
            trace.get_tracer(
                __name__, __version__, tracer_provider=tracer_provider,
            ),
        )
        wrap_function_wrapper(aioredis, "Redis.execute", traced_execute)

    def _uninstrument(self, **kwargs):
        unwrap(aioredis.Redis, "execute")
