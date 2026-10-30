# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


from confluent_kafka import Consumer, Producer


class MockConsumer(Consumer):
    def __init__(self, queue, config):
        self._queue = queue
        self.config = config
        self._current_consume_span = None
        self._current_context_token = None
        super().__init__(config)

    def consume(self, num_messages=1, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        messages = self._queue[:num_messages]
        self._queue = self._queue[num_messages:]
        return messages

    def poll(self, timeout=None):
        if len(self._queue) > 0:
            return self._queue.pop(0)
        return None


class MockedMessage:
    def __init__(
        self,
        topic: str,
        partition: int,
        offset: int,
        headers,
        key: str | None = None,
        value: str | None = None,
    ):
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._headers = headers
        self._key = key
        self._value = value

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def headers(self):
        return self._headers

    def key(self):
        return self._key

    def value(self):
        return self._value


class MockedProducer(Producer):
    def __init__(self, queue, config):
        self._queue = queue
        self.config = config
        super().__init__(config)

    def produce(self, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        self._queue.append(
            MockedMessage(
                topic=kwargs.get("topic"),
                partition=0,
                offset=0,
                headers=[],
                key=kwargs.get("key"),
                value=kwargs.get("value"),
            )
        )

    def poll(self, *args, **kwargs):
        return len(self._queue)

    def flush(self, *args, **kwargs):
        return len(self._queue)


class MockedAIOProducer:
    def __init__(self, config=None):
        self._queue = []
        self.config = config or {}

    async def produce(self, topic, value=None, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        msg = MockedMessage(
            topic=topic,
            partition=0,
            offset=0,
            headers=kwargs.get("headers", []),
            key=kwargs.get("key"),
            value=value,
        )
        self._queue.append(msg)
        return msg


class MockedAIOConsumer:
    """Mock of confluent_kafka.AIOConsumer.

    The real AIOConsumer delegates polling to an inner sync Consumer, which when
    instrumented already creates spans via wrap_poll.  This mock mirrors that
    structure so tests can verify that no duplicate spans are produced at the
    AIO layer.
    """

    def __init__(self, queue, config=None):
        self._inner = MockConsumer(queue, config or {})
        self.config = config or {}

    async def poll(self, timeout=None):
        # Delegate to the inner consumer, just like the real AIOConsumer does.
        return self._inner.poll(timeout)

    async def close(self):
        pass
