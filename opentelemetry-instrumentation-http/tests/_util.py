# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any
from unittest import TestCase

from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
)
from opentelemetry.trace import Link, SpanKind, TraceState
from opentelemetry.util.types import Attributes


class CaseInsensitiveHeaders(Mapping[str, "str | Sequence[str]"]):
    """Looks up header names case-insensitively, but iterates over them in their original case."""

    def __init__(self, headers: Mapping[str, str | Sequence[str]]) -> None:
        self._headers = dict(headers)
        self._names = {name.lower(): name for name in headers}

    def __getitem__(self, name: str) -> str | Sequence[str]:
        return self._headers[self._names[name.lower()]]

    def __iter__(self) -> Iterator[str]:
        return iter(self._headers)

    def __len__(self) -> int:
        return len(self._headers)


class RecordingSampler(Sampler):
    """Records the attributes available when each span is sampled."""

    def __init__(self) -> None:
        self.attributes: list[dict[str, Any]] = []

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
        self.attributes.append(dict(attributes or {}))
        return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

    def get_description(self) -> str:
        return "RecordingSampler"


@contextmanager
def assert_logs(
    test: TestCase,
    level: int | str = logging.WARNING,
    *,
    contains: str | None = None,
    present: bool = True,
) -> Iterator[None]:
    """Asserts that a record at ``level`` or above is logged, whose message includes ``contains`` if given.

    With ``present=False``, asserts instead that nothing at ``level`` or above is logged.
    """
    if not present:
        with test.assertNoLogs(level=level):
            yield
        return
    with test.assertLogs(level=level) as logs:
        yield
    if contains is not None:
        test.assertTrue(
            any(contains in record.getMessage() for record in logs.records),
            f"no log record containing {contains!r}: {logs.output}",
        )


def _value_type(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(type(item) for item in value)
    return type(value)


def assert_attributes(test: TestCase, actual: Mapping[str, Any] | None, expected: Mapping[str, Any]) -> None:
    """Asserts that ``actual`` holds exactly the ``expected`` attributes, with values of the same types."""
    attributes = dict(actual or {})
    test.assertEqual(attributes, dict(expected))
    test.assertEqual(
        {key: _value_type(value) for key, value in attributes.items()},
        {key: _value_type(value) for key, value in expected.items()},
    )
