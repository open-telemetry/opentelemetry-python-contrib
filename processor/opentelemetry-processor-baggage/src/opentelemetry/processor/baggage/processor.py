# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Callable, Optional, Sequence, Union

from opentelemetry.baggage import get_all as get_all_baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.trace import Span

# A BaggageKeyPredicate is a function that takes a baggage key and returns a boolean
BaggageKeyPredicateT = Callable[[str], bool]
BaggageKeyPredicates = Union[
    BaggageKeyPredicateT, Sequence[BaggageKeyPredicateT]
]

# A BaggageKeyPredicate that always returns True, allowing all baggage keys to be added to spans
ALLOW_ALL_BAGGAGE_KEYS: BaggageKeyPredicateT = lambda _: True  # noqa: E731 # pylint:disable=invalid-name


class BaggageSpanProcessor(SpanProcessor):
    """
    The BaggageSpanProcessor reads entries stored in Baggage
    from the parent context and adds the baggage entries' keys and
    values to the span as attributes on span start.

    Add this span processor to a tracer provider.

    Keys and values added to Baggage will appear on subsequent child
    spans for a trace within this service *and* be propagated to external
    services in accordance with any configured propagation formats
    configured. If the external services also have a Baggage span
    processor, the keys and values will appear in those child spans as
    well.

    ⚠ Warning ⚠️

    Do not put sensitive information in Baggage.

    To repeat: a consequence of adding data to Baggage is that the keys and
    values will appear in all outgoing HTTP headers from the application.

    """

    def __init__(self, baggage_key_predicate: BaggageKeyPredicates) -> None:
        if callable(baggage_key_predicate):
            self._predicates = [baggage_key_predicate]
        else:
            self._predicates = list(baggage_key_predicate)

    def on_start(
        self, span: "Span", parent_context: Optional[Context] = None
    ) -> None:
        baggage = get_all_baggage(parent_context)
        for key, value in baggage.items():
            if any(predicate(key) for predicate in self._predicates):
                span.set_attribute(key, value)
