# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_HEADER_TEMPLATE,
)
from opentelemetry.trace import Link, SpanKind, TraceState
from opentelemetry.util.types import Attributes, AttributeValue

CUSTOM_REQUEST_HEADER_ATTRIBUTE = f"{HTTP_REQUEST_HEADER_TEMPLATE}.custom_test_header_1"


def request_header_attributes(attributes: Attributes) -> dict[str, AttributeValue]:
    """Returns the captured request header attributes in ``attributes``."""
    return {
        key: value for key, value in (attributes or {}).items() if key.startswith(f"{HTTP_REQUEST_HEADER_TEMPLATE}.")
    }


class RequestHeaderSampler(Sampler):
    """Records what the SDK passes to ``should_sample``.

    When ``required_value`` is set, spans are dropped unless the captured
    ``Custom-Test-Header-1`` request header has that value.
    """

    attributes: dict[str, AttributeValue]
    kind: SpanKind | None
    required_value: str | None

    def __init__(self, required_value: str | None = None) -> None:
        self.attributes = {}
        self.kind = None
        self.required_value = required_value

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        # Snapshot now so attributes set after span creation cannot hide a regression.
        self.attributes = dict(attributes or {})
        self.kind = kind
        decision = Decision.RECORD_AND_SAMPLE
        if self.required_value is not None and self.attributes.get(CUSTOM_REQUEST_HEADER_ATTRIBUTE) != [
            self.required_value
        ]:
            decision = Decision.DROP
        return SamplingResult(decision, attributes=self.attributes, trace_state=trace_state)

    def get_description(self) -> str:
        return "RequestHeaderSampler"
