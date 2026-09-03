# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


from confluent_kafka import Consumer, Producer


class MockClusterMetadata:
    def __init__(self, cluster_id: str | None = None) -> None:
        self.cluster_id = cluster_id
        self.brokers: dict = {}
        self.topics: dict = {}


class MockConsumer(Consumer):
    def __init__(self, queue, config):
        self._queue = queue
        self.config = config
        self._mock_cluster_id: str | None = None
        super().__init__(config)

    def consume(self, num_messages=1, *args, **kwargs):  # pylint: disable=keyword-arg-before-vararg
        messages = self._queue[:num_messages]
        self._queue = self._queue[num_messages:]
        return messages

    def poll(self, timeout=None):
        if len(self._queue) > 0:
            return self._queue.pop(0)
        return None

    def list_topics(self, topic=None, timeout=-1):
        return MockClusterMetadata(cluster_id=self._mock_cluster_id)


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
        self._mock_cluster_id: str | None = None
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

    def list_topics(self, topic=None, timeout=-1):
        return MockClusterMetadata(cluster_id=self._mock_cluster_id)
