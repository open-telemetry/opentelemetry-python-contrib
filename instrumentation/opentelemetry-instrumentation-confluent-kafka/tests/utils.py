from confluent_kafka import Consumer


class MockConsumer(Consumer):
    def __init__(self, queue, config):
        self._queue = queue
        super().__init__(config)

    def consume(
        self, num_messages=1, *args, **kwargs
    ):  # pylint: disable=keyword-arg-before-vararg
        messages = self._queue[:num_messages]
        self._queue = self._queue[num_messages:]
        return messages

    def poll(self, timeout=None):
        if len(self._queue) > 0:
            return self._queue.pop(0)
        return None


class MockedMessage:
    def __init__(self, topic: str, partition: int, offset: int, headers):
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._headers = headers

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def headers(self):
        return self._headers
