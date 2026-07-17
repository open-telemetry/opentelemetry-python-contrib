# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Callable

from opentelemetry.instrumentation.cidict import CIDict
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.textmap import Getter
from opentelemetry.semconv._incubating.attributes.messaging_attributes import (
    MESSAGING_BATCH_MESSAGE_COUNT,
    MESSAGING_DESTINATION_NAME,
    MESSAGING_MESSAGE_ID,
    MESSAGING_OPERATION_TYPE,
    MESSAGING_SYSTEM,
    MessagingOperationTypeValues,
    MessagingSystemValues,
)
from opentelemetry.trace import Link, SpanKind, get_current_span

logger = logging.getLogger(__name__)

CarrierT = dict[str, Any]


class _SqsMessageAttributesGetter(Getter[CarrierT]):
    """Extracts W3C trace context from SQS message attribute dicts.

    SQS message attributes have the structure:
    ``{"traceparent": {"dataType": "String", "stringValue": "00-..."}}``.
    """

    def get(self, carrier: CarrierT, key: str) -> list[str] | None:
        msg_attr = carrier.get(key)
        if not isinstance(msg_attr, Mapping):
            return None
        value = msg_attr.get("stringValue")
        return [value] if isinstance(value, str) else None

    def keys(self, carrier: CarrierT) -> list[str]:
        return list(carrier.keys())


_sqs_getter = _SqsMessageAttributesGetter()


def _is_sqs_event(lambda_event: Any) -> bool:
    try:
        return bool(
            isinstance(lambda_event, dict)
            and isinstance(lambda_event.get("Records"), list)
            and lambda_event["Records"]
            and lambda_event["Records"][0]
            .get("eventSource", "")
            .strip()
            .lower()
            == "aws:sqs"
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "An unexpected error occurred while checking SQS event: %s", exc
        )
        return False


def _extract_sqs_queue_name(arn: str) -> str:
    parts = arn.split(":")
    return parts[5] if len(parts) >= 6 else arn


def _get_sqs_span_links(records: list[dict[str, Any]]) -> list[Link]:
    links = []
    for record in records:
        msg_attrs = record.get("messageAttributes") or {}
        if not msg_attrs or not isinstance(msg_attrs, dict):
            continue
        # Wrap in CIDict so propagation header name lookup is case-insensitive
        # (e.g. "TRACEPARENT" and "traceparent" are both found).
        ctx = get_global_textmap().extract(
            CIDict(msg_attrs), getter=_sqs_getter
        )
        span_ctx = get_current_span(ctx).get_span_context()
        if span_ctx and span_ctx.is_valid:
            links.append(
                Link(
                    context=span_ctx,
                    attributes={
                        MESSAGING_MESSAGE_ID: record.get("messageId", "")
                    },
                )
            )
    return links


def _run_sqs_handler(
    tracer: Any,
    lambda_event: dict[str, Any],
    handler: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    records: list[dict[str, Any]] = lambda_event["Records"]
    queue_name = _extract_sqs_queue_name(records[0].get("eventSourceARN", ""))
    links = _get_sqs_span_links(records)
    attrs: dict[str, Any] = {
        MESSAGING_SYSTEM: MessagingSystemValues.AWS_SQS.value,
        MESSAGING_DESTINATION_NAME: queue_name,
        MESSAGING_OPERATION_TYPE: MessagingOperationTypeValues.PROCESS.value,
    }
    if len(records) > 1:
        attrs[MESSAGING_BATCH_MESSAGE_COUNT] = len(records)

    with tracer.start_as_current_span(
        f"process {queue_name}".strip(),
        kind=SpanKind.CONSUMER,
        links=links,
        attributes=attrs,
    ):
        return handler(*args, **kwargs)
