# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Sequence
from typing import overload

from opentelemetry.baggage import get_all as get_all_baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.trace import Span

# A BaggageKeyPredicate is a function that takes a baggage key and returns a boolean
BaggageKeyPredicateT = Callable[[str], bool]
BaggageKeyPredicates = BaggageKeyPredicateT | Sequence[BaggageKeyPredicateT]

# A BaggageKeyPredicate that always returns True, allowing all baggage keys to be added to spans
ALLOW_ALL_BAGGAGE_KEYS: BaggageKeyPredicateT = lambda _: True  # pylint:disable=invalid-name  # noqa: E731


def _compile_globs(patterns: Collection[str]) -> re.Pattern[str] | None:
    """Compile wildcard patterns into a single regex.

    Only ``*`` (any number of any character) and ``?`` (any single character)
    are treated as wildcards, every other character matches literally.
    """
    if not patterns:
        return None
    return re.compile(
        "|".join("(?:" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + ")" for pattern in patterns)
    )


def _baggage_key_predicates(
    baggage_key_predicate: BaggageKeyPredicates | None,
    included: Collection[str] | None,
    excluded: Collection[str] | None,
) -> list[BaggageKeyPredicateT]:
    if baggage_key_predicate is not None:
        if included is not None or excluded is not None:
            raise ValueError("baggage_key_predicate cannot be combined with included or excluded")
        if callable(baggage_key_predicate):
            return [baggage_key_predicate]
        return list(baggage_key_predicate)

    included_regex = _compile_globs(included or ())
    excluded_regex = _compile_globs(excluded or ())
    if included_regex is None and excluded_regex is None:
        return [ALLOW_ALL_BAGGAGE_KEYS]

    def _include_exclude(key: str) -> bool:
        if included_regex is not None and not included_regex.fullmatch(key):
            return False
        return excluded_regex is None or not excluded_regex.fullmatch(key)

    return [_include_exclude]


class BaggageSpanProcessor(SpanProcessor):
    """
    The BaggageSpanProcessor reads entries stored in Baggage
    from the parent context and adds the baggage entries' keys and
    values to the span as attributes on span start.

    Add this span processor to a tracer provider.

    Baggage keys are selected either with ``baggage_key_predicate`` or with
    ``included`` / ``excluded`` wildcard patterns, which cannot be combined.
    Patterns support ``*`` and ``?`` and are matched case-sensitively against
    the whole key. When ``included`` is empty or not set, all keys are
    included; ``excluded`` is applied after ``included``. When nothing is
    configured, all baggage entries are copied.

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

    @overload
    def __init__(self, baggage_key_predicate: BaggageKeyPredicates) -> None: ...

    @overload
    def __init__(
        self,
        *,
        included: Collection[str] | None = None,
        excluded: Collection[str] | None = None,
    ) -> None: ...

    def __init__(
        self,
        baggage_key_predicate: BaggageKeyPredicates | None = None,
        *,
        included: Collection[str] | None = None,
        excluded: Collection[str] | None = None,
    ) -> None:
        self._predicates = _baggage_key_predicates(baggage_key_predicate, included, excluded)

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        baggage = get_all_baggage(parent_context)
        for key, value in baggage.items():
            if any(predicate(key) for predicate in self._predicates):
                span.set_attribute(key, value)
