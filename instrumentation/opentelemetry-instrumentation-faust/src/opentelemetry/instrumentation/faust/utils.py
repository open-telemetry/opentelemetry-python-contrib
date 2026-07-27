# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import contextlib
import json
from collections.abc import Mapping, MutableMapping, MutableSequence
from logging import getLogger
from typing import TYPE_CHECKING

from opentelemetry.propagators import textmap
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from typing import Iterable, List, Tuple, Union

    from yarl import URL

    # Kafka message headers in the shapes faust passes them around:
    # either a (mutable) mapping of name to value or a list of tuples.
    HeadersArg = Union[
        MutableMapping[str, bytes],
        Mapping[str, bytes],
        MutableSequence[Tuple[str, bytes]],
        List[Tuple[str, bytes]],
    ]

_LOG = getLogger(__name__)


def _header_items(carrier: HeadersArg) -> Iterable[tuple[str, object]]:
    if isinstance(carrier, Mapping):
        return carrier.items()
    return carrier


class FaustContextGetter(textmap.Getter["HeadersArg"]):
    def get(self, carrier: HeadersArg | None, key: str) -> list[str] | None:
        if carrier is None:
            return None
        for item_key, value in _header_items(carrier):
            if item_key == key and value is not None:
                if isinstance(value, bytes):
                    with contextlib.suppress(UnicodeDecodeError):
                        return [value.decode()]
                    return None
                return [str(value)]
        return None

    def keys(self, carrier: HeadersArg | None) -> list[str]:
        if carrier is None:
            return []
        return [key for (key, _) in _header_items(carrier)]


class FaustContextSetter(textmap.Setter["HeadersArg"]):
    def set(
        self, carrier: HeadersArg | None, key: str | None, value: str | None
    ) -> None:
        if carrier is None or key is None or value is None:
            return
        if isinstance(carrier, MutableMapping):
            carrier[key] = value.encode()
        elif isinstance(carrier, MutableSequence):
            carrier.append((key, value.encode()))
        else:
            _LOG.warning(
                "Unable to set context in headers. Headers is immutable"
            )


_faust_getter = FaustContextGetter()
_faust_setter = FaustContextSetter()


def _deserialize_key(key: object | None) -> str | None:
    if key is None:
        return None

    if isinstance(key, bytes):
        with contextlib.suppress(UnicodeDecodeError):
            return key.decode()
        return None

    return str(key)


def _get_span_name(operation: str, topic: str) -> str:
    return f"{topic} {operation}"


def _serialize_broker_urls(broker_urls: list[URL]) -> str:
    return json.dumps([str(broker_url) for broker_url in broker_urls])


def _build_base_attributes(
    *,
    broker_urls: list[URL],
    client_id: str,
    topic: str,
    partition: int | None,
    key: str | None,
) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {
        messaging_attributes.MESSAGING_SYSTEM: messaging_attributes.MessagingSystemValues.KAFKA.value,
        server_attributes.SERVER_ADDRESS: _serialize_broker_urls(broker_urls),
        messaging_attributes.MESSAGING_CLIENT_ID: client_id,
        messaging_attributes.MESSAGING_DESTINATION_NAME: topic,
    }
    if partition is not None:
        attributes[messaging_attributes.MESSAGING_DESTINATION_PARTITION_ID] = (
            str(partition)
        )
    if key is not None:
        attributes[messaging_attributes.MESSAGING_KAFKA_MESSAGE_KEY] = key
    return attributes


def _build_send_attributes(
    *,
    broker_urls: list[URL],
    client_id: str,
    topic: str,
    partition: int | None,
    key: str | None,
) -> dict[str, AttributeValue]:
    attributes = _build_base_attributes(
        broker_urls=broker_urls,
        client_id=client_id,
        topic=topic,
        partition=partition,
        key=key,
    )
    attributes[messaging_attributes.MESSAGING_OPERATION_NAME] = "send"
    attributes[messaging_attributes.MESSAGING_OPERATION_TYPE] = (
        messaging_attributes.MessagingOperationTypeValues.PUBLISH.value
    )
    return attributes


def _build_process_attributes(
    *,
    broker_urls: list[URL],
    client_id: str,
    consumer_group: str | None,
    topic: str,
    partition: int,
    offset: int,
    key: str | None,
) -> dict[str, AttributeValue]:
    attributes = _build_base_attributes(
        broker_urls=broker_urls,
        client_id=client_id,
        topic=topic,
        partition=partition,
        key=key,
    )
    attributes[messaging_attributes.MESSAGING_OPERATION_NAME] = "process"
    attributes[messaging_attributes.MESSAGING_OPERATION_TYPE] = (
        messaging_attributes.MessagingOperationTypeValues.PROCESS.value
    )
    if consumer_group is not None:
        attributes[messaging_attributes.MESSAGING_CONSUMER_GROUP_NAME] = (
            consumer_group
        )
    attributes[messaging_attributes.MESSAGING_KAFKA_MESSAGE_OFFSET] = offset
    # A message within Kafka is uniquely defined by its topic name,
    # topic partition and offset.
    attributes[messaging_attributes.MESSAGING_MESSAGE_ID] = (
        f"{topic}.{partition}.{offset}"
    )
    return attributes
