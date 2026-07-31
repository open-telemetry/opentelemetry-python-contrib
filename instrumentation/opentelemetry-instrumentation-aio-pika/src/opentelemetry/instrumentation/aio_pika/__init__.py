# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Instrument aio_pika to trace RabbitMQ applications.

Usage
-----
Start broker backend

.. code-block:: python

    docker run -p 5672:5672 rabbitmq

Run instrumented task

.. code-block:: python

    import asyncio

    from aio_pika import Message, connect
    from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor

    AioPikaInstrumentor().instrument()


    async def main() -> None:
        connection = await connect("amqp://guest:guest@localhost/")
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue("hello")
            await channel.default_exchange.publish(
                Message(b"Hello World!"),
                routing_key=queue.name)

    if __name__ == "__main__":
        asyncio.run(main())

API
---
"""
# pylint: disable=import-error

from .aio_pika_instrumentor import AioPikaInstrumentor
from .version import __version__

__all__ = ["AioPikaInstrumentor", "__version__"]
