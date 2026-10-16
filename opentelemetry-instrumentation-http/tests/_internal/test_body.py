# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest import TestCase

from opentelemetry.instrumentation.http._internal._body import (
    BodyContentCapture,
    get_charset,
    is_textual_content_type,
)


class TestIsTextualContentType(TestCase):
    def test_is_textual_content_type(self) -> None:
        for content_type, expected in (
            ("text/plain", True),
            ("text/html; charset=utf-8", True),
            ("application/json", True),
            ("application/problem+json", True),
            ("application/xml", True),
            ("image/svg+xml", True),
            ("application/yaml", True),
            ("application/vnd.api+yaml", True),
            ("application/x-www-form-urlencoded", True),
            ("application/octet-stream; charset=utf-8", True),
            ("APPLICATION/JSON; Charset=UTF-8", True),
            (" text/csv ", True),
            (None, False),
            ("", False),
            ("application/octet-stream", False),
            ("image/png", False),
            ("multipart/form-data; boundary=abc", False),
            ("application/jsonl", False),
            ("application/json-seq", False),
            ("application/octet-stream; charset=", False),
            ("bogus", False),
        ):
            with self.subTest(content_type=content_type):
                self.assertIs(is_textual_content_type(content_type), expected)


class TestGetCharset(TestCase):
    def test_charset(self) -> None:
        for content_type, expected in (
            ("text/plain; charset=latin-1", "latin-1"),
            ('text/plain; charset="iso-8859-1"', "iso-8859-1"),
            ("text/plain;CHARSET=utf-16", "utf-16"),
            ("text/plain; charset=UTF-8", "utf-8"),
            ("text/plain; charset*=utf-8''UTF-8", "utf-8"),
            ("text/plain", "utf-8"),
            ("text/plain; charset=", "utf-8"),
            ("text/plain; charset=unknown-charset", "utf-8"),
            ("text/plain; charset=base64_codec", "utf-8"),
            ("text/plain; charset=rot_13", "utf-8"),
            (None, "utf-8"),
        ):
            with self.subTest(content_type=content_type):
                self.assertEqual(get_charset(content_type), expected)


class TestBodyContentCapture(TestCase):
    def test_get_content(self) -> None:
        for max_size, chunks, content_type, expected in (
            # Nothing added.
            (None, (), "text/plain", None),
            (None, (b"",), "text/plain", ""),
            # Not textual.
            (None, (b"\x89PNG",), "image/png", None),
            (None, (b"\x89PNG",), None, None),
            (None, (b'{"a": ', b"1}"), "application/json", '{"a": 1}'),
            (None, ("café".encode("latin-1"),), "text/plain; charset=latin-1", "café"),
            # Unbounded.
            (None, (b"a" * 10_000,), "text/plain", "a" * 10_000),
            (0, (b"a" * 10_000,), "text/plain", "a" * 10_000),
            (-1, (b"a" * 10_000,), "text/plain", "a" * 10_000),
            # Truncated.
            (5, (b"abc", b"defg", b"hij"), "text/plain", "abcde"),
            (4, ("abé".encode(),), "text/plain", "abé"),
            (3, ("abé".encode(),), "text/plain", "ab"),
            # Invalid bytes, or an incomplete character without truncation, are replaced.
            (None, (b"a\xffb",), "text/plain", "a�b"),
            (None, ("é".encode()[:1],), "text/plain", "�"),
            # Content that cannot be decoded is not returned.
            (None, (b"h\x00i\x00",), "text/plain; charset=utf-16", None),
            (None, (b"h\x00\x00\x00",), "text/plain; charset=utf-32", None),
            (None, (b"abc",), "text/plain; charset=idna", None),
            # Non-text codecs fall back to UTF-8.
            (None, (b"aGk=",), "text/plain; charset=base64_codec", "aGk="),
        ):
            with self.subTest(max_size=max_size, chunks=chunks, content_type=content_type):
                capture = BodyContentCapture(max_size)
                for chunk in chunks:
                    capture.add(chunk)

                self.assertEqual(capture.get_content(content_type), expected)
