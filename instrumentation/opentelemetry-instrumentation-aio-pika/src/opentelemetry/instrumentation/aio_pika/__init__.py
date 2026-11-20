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
            await channel.default_exchange.publish(Message(b"Hello World!"), routing_key=queue.name)


    if __name__ == "__main__":
        asyncio.run(main())

Hooks
-----
AioPikaInstrumentor also supports instrumenting with hooks that will be called when producing or consuming a message.
The hooks should be of type "Callable[[Span, AbstractMessage], None]" for publish_hook and
"Callable[[Span, AbstractIncomingMessage], None]" for consume_hook.

.. code-block:: python

    from aio_pika.abc import AbstractMessage, AbstractIncomingMessage
    from opentelemetry.trace import Span

    def publish_hook(span: Span, message: AbstractMessage):
        span.set_attribute("custom.publish.tag", "my-value")

    def consume_hook(span: Span, message: AbstractIncomingMessage):
        span.set_attribute("custom.consume.tag", "my-value")

    AioPikaInstrumentor().instrument(publish_hook=publish_hook, consume_hook=consume_hook)

API
---
"""
# pylint: disable=import-error

from .aio_pika_instrumentor import AioPikaInstrumentor
from .version import __version__

__all__ = ["AioPikaInstrumentor", "__version__"]
