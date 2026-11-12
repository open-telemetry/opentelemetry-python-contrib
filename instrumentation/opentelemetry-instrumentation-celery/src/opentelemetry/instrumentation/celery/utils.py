# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast

from celery import registry  # pylint: disable=no-name-in-module
from celery.app.task import Task
from kombu import Exchange, Queue

from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_MESSAGE_ID,
)
from opentelemetry.semconv.trace import MessagingDestinationKindValues, SpanAttributes
from opentelemetry.trace import Span
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

ContextKey = tuple[str, bool]
ContextTuple = tuple[Span, "AbstractContextManager[Span]", object | None]
ContextDict = dict[ContextKey, ContextTuple]


class ContextCarrier(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...


logger = logging.getLogger(__name__)

# Celery Context key
CTX_KEY = "__otel_task_span"

# Metadata read from top-level task.request fields. Entries marked "optional"
# are retained for compatibility with explicitly supplied request metadata
# (e.g. custom message headers); normal publishing does not populate them here.
CELERY_REQUEST_ATTRIBUTES: tuple[str, ...] = (
    "compression",
    "correlation_id",
    "countdown",  # Optional: Celery converts the publishing countdown to eta.
    "delivery_info",
    "eta",
    "exchange",  # Optional: normally nested in delivery_info.
    "expires",
    "hostname",
    "id",
    "priority",  # Optional: normally nested in delivery_info.
    "queue",  # Optional: the publishing queue is not copied to task.request.
    "reply_to",
    "retries",
    "routing_key",  # Optional: normally nested in delivery_info.
    "serializer",  # Optional: serialization is represented by the message content_type.
    "timelimit",
    "origin",
)


def get_publish_attributes(context: Mapping[str, Any]) -> dict[str, AttributeValue]:
    """Extract routing metadata from before_task_publish signal arguments."""
    attributes: dict[str, AttributeValue] = {}
    exchange = context.get("exchange")
    if isinstance(exchange, Exchange):
        exchange = exchange.name
    if exchange is not None and exchange != "":
        attributes["celery.exchange"] = exchange

    routing_key = context.get("routing_key")
    if routing_key is not None and routing_key != "":
        attributes[SpanAttributes.MESSAGING_DESTINATION] = routing_key

    # according to https://docs.celeryproject.org/en/stable/userguide/routing.html#exchange-types
    for declare in context.get("declare") or ():
        if declare.exchange.type == "direct":
            attributes[SpanAttributes.MESSAGING_DESTINATION_KIND] = MessagingDestinationKindValues.QUEUE.value
            break
        if declare.exchange.type == "topic":
            attributes[SpanAttributes.MESSAGING_DESTINATION_KIND] = MessagingDestinationKindValues.TOPIC.value
            break

    return attributes


# pylint:disable=too-many-branches
def get_request_attributes(context: ContextCarrier) -> dict[str, AttributeValue]:
    """Extract execution metadata from task.request."""
    attributes: dict[str, AttributeValue] = {}
    for key in CELERY_REQUEST_ATTRIBUTES:
        value = context.get(key)

        # Skip this key if it is not set
        if value is None or value == "":
            continue

        # Skip `timelimit` if it is not set (it's default/unset value is a
        # tuple or a list of `None` values
        if key == "timelimit":
            if value in [(None, None), [None, None]]:
                continue
            if None in value:
                value = ["" if tl is None else str(tl) for tl in value]

        # Skip `retries` if it's value is `0`
        if key == "retries" and value == 0:
            continue

        attribute_name = None
        if key == "delivery_info":
            # Get also destination from this
            routing_key = value.get("routing_key")
            if routing_key is not None:
                attributes[SpanAttributes.MESSAGING_DESTINATION] = routing_key
            value = str(value)
        elif key == "id":
            attribute_name = MESSAGING_MESSAGE_ID
        elif key == "correlation_id":
            attribute_name = SpanAttributes.MESSAGING_CONVERSATION_ID
        elif key == "routing_key":
            attribute_name = SpanAttributes.MESSAGING_DESTINATION

        # set attribute name if not set specially for a key
        if attribute_name is None:
            attribute_name = f"celery.{key}"

        if isinstance(value, (Exchange, Queue)):
            value = value.name
            if value == "":
                continue

        attributes[attribute_name] = value

    return attributes


def attach_context(
    task: Task | None,
    task_id: str,
    span: Span,
    activation: AbstractContextManager[Span],
    token: object | None,
    is_publish: bool = False,
) -> None:
    """Helper to propagate a `Span`, `ContextManager` and context token
    for the given `Task` instance. This function uses a `dict` that stores
    the Span using the `(task_id, is_publish)` as a key. This is useful
    when information must be propagated from one Celery signal to another.

    We use (task_id, is_publish) for the key to ensure that publishing a
    task from within another task does not cause any conflicts.

    This mostly happens when either a task fails and a retry policy is in place,
    or when a task is manually retries (e.g. `task.retry()`), we end up trying
    to publish a task with the same id as the task currently running.

    Previously publishing the new task would overwrite the existing `celery.run` span
    in the `dict` causing that span to be forgotten and never finished
    NOTE: We cannot test for this well yet, because we do not run a celery worker,
    and cannot run `task.apply_async()`
    """
    if task is None:
        return

    ctx_dict = cast(ContextDict | None, getattr(task, CTX_KEY, None))

    if ctx_dict is None:
        ctx_dict = {}
        setattr(task, CTX_KEY, ctx_dict)

    ctx_dict[(task_id, is_publish)] = (span, activation, token)


def detach_context(task: Task | None, task_id: str, is_publish: bool = False) -> None:
    """Helper to remove  `Span`, `ContextManager` and context token in a
    Celery task when it's propagated.
    This function handles tasks where no values are attached to the `Task`.
    """
    if task is None:
        return

    span_dict = cast(ContextDict | None, getattr(task, CTX_KEY, None))
    if span_dict is None:
        return

    # See note in `attach_context` for key info
    span_dict.pop((task_id, is_publish), None)


def retrieve_context(task: Task | None, task_id: str, is_publish: bool = False) -> ContextTuple | None:
    """Helper to retrieve an active `Span`, `ContextManager` and context token
    stored in a `Task` instance
    """
    if task is None:
        return None

    span_dict = cast(ContextDict | None, getattr(task, CTX_KEY, None))
    if span_dict is None:
        return None

    # See note in `attach_context` for key info
    return span_dict.get((task_id, is_publish), None)


def retrieve_task(kwargs: Mapping[str, Any]) -> Task | None:
    task = kwargs.get("task")
    if task is None:
        logger.debug("Unable to retrieve task from signal arguments")
    return cast(Task | None, task)


def retrieve_task_from_sender(kwargs: Mapping[str, Any]) -> Task | None:
    sender = kwargs.get("sender")
    if sender is None:
        logger.debug("Unable to retrieve the sender from signal arguments")

    # before and after publish signals sender is the task name
    # for retry and failure signals sender is the task object
    if isinstance(sender, str):
        sender = registry.tasks.get(sender)
        if sender is None:
            logger.debug("Unable to retrieve the task from sender=%s", sender)

    return cast(Task | None, sender)


def retrieve_task_id(kwargs: Mapping[str, Any]) -> str | None:
    task_id = kwargs.get("task_id")
    if task_id is None:
        logger.debug("Unable to retrieve task_id from signal arguments")
    return cast(str | None, task_id)


def retrieve_task_id_from_request(kwargs: Mapping[str, Any]) -> str | None:
    # retry signal does not include task_id as argument so use request argument
    request = kwargs.get("request")
    if request is None:
        logger.debug("Unable to retrieve the request from signal arguments")
        return None

    task_id = cast(str | None, getattr(request, "id", None))
    if task_id is None:
        logger.debug("Unable to retrieve the task_id from the request")

    return task_id


def retrieve_task_id_from_message(kwargs: Mapping[str, Any]) -> str | None:
    """Helper to retrieve the `Task` identifier from the message `body`.
    This helper supports Protocol Version 1 and 2. The Protocol is well
    detailed in the official documentation:
    http://docs.celeryproject.org/en/latest/internals/protocol.html
    """
    headers = kwargs.get("headers")
    body = kwargs.get("body")
    if headers is not None and len(headers) > 0:
        # Protocol Version 2 (default from Celery 4.0)
        return cast(str | None, headers.get("id"))
    # Protocol Version 1
    if body is None:
        return None
    return cast(str | None, body.get("id"))


def retrieve_reason(kwargs: Mapping[str, Any]) -> object | None:
    reason = kwargs.get("reason")
    if not reason:
        logger.debug("Unable to retrieve the retry reason")
    return reason
