# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any
from unittest import TestCase

from tests._util import assert_attributes

from opentelemetry.instrumentation.http._internal._headers import HeaderCapture
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_HEADER_TEMPLATE,
)

_Patterns = Collection[str | re.Pattern[str]] | None

_CUSTOM_HEADER = {"X-Custom-Header": "1"}
_CUSTOM_HEADER_ATTRIBUTE = {"http.request.header.x-custom-header": ("1",)}


class TestHeaderCapture(TestCase):
    _CASES: tuple[tuple[_Patterns, _Patterns, Mapping[str, str | Sequence[str]] | None, dict[str, Any]], ...] = (
        # Nothing captured.
        (None, None, {"Content-Type": "text/plain"}, {}),
        ([], None, {"Content-Type": "text/plain"}, {}),
        ((), None, {"Content-Type": "text/plain"}, {}),
        # No headers.
        (["content-type"], None, None, {}),
        (["content-type"], None, {}, {}),
        # Keys are lowercased and values are tuples of strings.
        (["content-type"], None, {"Content-Type": "text/plain"}, {"http.request.header.content-type": ("text/plain",)}),
        (
            ["x-a", "x-b", "x-c"],
            None,
            {"x-a": "1", "x-b": ["1", "2"], "x-c": ("3",)},
            {
                "http.request.header.x-a": ("1",),
                "http.request.header.x-b": ("1", "2"),
                "http.request.header.x-c": ("3",),
            },
        ),
        # Duplicate names are merged.
        (["x-a"], None, {"X-A": "1", "x-a": ["2", "3"]}, {"http.request.header.x-a": ("1", "2", "3")}),
        # Uncaptured headers are skipped.
        (["x-a"], None, {"x-a": "1", "x-b": "2"}, {"http.request.header.x-a": ("1",)}),
        # Strings match case-insensitively and are not patterns.
        (["X-Custom"], None, {"x-CUSTOM": "1"}, {"http.request.header.x-custom": ("1",)}),
        (["x-.*"], None, {"x-a": "1"}, {}),
        # Patterns must fully match the lowercased name.
        ([re.compile("x-custom-.*")], None, _CUSTOM_HEADER, _CUSTOM_HEADER_ATTRIBUTE),
        ([re.compile("x-custom")], None, _CUSTOM_HEADER, {}),
        ([re.compile("custom-header")], None, _CUSTOM_HEADER, {}),
        ([re.compile("X-CUSTOM-HEADER")], None, _CUSTOM_HEADER, {}),
        ([re.compile("X-CUSTOM-HEADER", re.IGNORECASE)], None, _CUSTOM_HEADER, _CUSTOM_HEADER_ATTRIBUTE),
        (
            ["x-a", re.compile("x-b-.*")],
            None,
            {"x-a": "1", "x-b-c": "2", "x-d": "3"},
            {"http.request.header.x-a": ("1",), "http.request.header.x-b-c": ("2",)},
        ),
        # Sanitized values are redacted.
        (
            ["authorization", "x-a"],
            ["Authorization"],
            {"Authorization": ["secret", "other"], "x-a": "1"},
            {
                "http.request.header.authorization": ("[REDACTED]", "[REDACTED]"),
                "http.request.header.x-a": ("1",),
            },
        ),
        (
            [re.compile("x-.*")],
            [re.compile(".*-token")],
            {"X-Auth-Token": "secret", "X-A": "1"},
            {"http.request.header.x-auth-token": ("[REDACTED]",), "http.request.header.x-a": ("1",)},
        ),
        # Sanitized but not captured headers are skipped.
        (["x-a"], ["authorization"], {"Authorization": "secret"}, {}),
    )

    def test_get_attributes(self) -> None:
        for captured, sanitized, headers, expected in self._CASES:
            with self.subTest(captured=captured, sanitized=sanitized, headers=headers):
                capture = HeaderCapture(
                    attribute_prefix=HTTP_REQUEST_HEADER_TEMPLATE, captured=captured, sanitized=sanitized
                )

                assert_attributes(self, capture.get_attributes(headers), expected)

    def test_attribute_prefix(self) -> None:
        capture = HeaderCapture(attribute_prefix="http.response.header", captured=["x-a"], sanitized=None)

        self.assertEqual(capture.get_attributes({"X-A": "1"}), {"http.response.header.x-a": ("1",)})
