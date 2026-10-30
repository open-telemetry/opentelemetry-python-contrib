# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import io
import unittest

from opentelemetry.util.http.body_capture import (
    BodyBuffer,
    CapturingStream,
    create_body_buffer,
)


class TestBodyBuffer(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(BodyBuffer(10, "text/plain").to_attribute_value())

    def test_truncates_to_max_size(self):
        buffer = BodyBuffer(5, "text/plain")
        buffer.write(0, b"hello world")
        self.assertEqual(buffer.to_attribute_value(), "hello")

    def test_rewrite_of_same_position_is_not_duplicated(self):
        buffer = BodyBuffer(100, "text/plain")
        buffer.write(0, b"hello")
        buffer.write(0, b"hello")
        buffer.write(5, b" world")
        self.assertEqual(buffer.to_attribute_value(), "hello world")

    def test_write_after_gap_is_ignored(self):
        buffer = BodyBuffer(100, "text/plain")
        buffer.write(0, b"ab")
        buffer.write(5, b"cd")
        self.assertEqual(buffer.to_attribute_value(), "ab")

    def test_textual_content_types_are_strings(self):
        for content_type in (
            "text/plain",
            "TEXT/HTML",
            "application/json",
            "application/vnd.api+json",
            "application/xml",
            "image/svg+xml",
            "application/yaml",
            "application/vnd.foo+yaml",
            "application/x-www-form-urlencoded",
            "application/octet-stream; charset=utf-8",
        ):
            with self.subTest(content_type=content_type):
                buffer = BodyBuffer(100, content_type)
                buffer.write(0, b"a=1")
                self.assertEqual(buffer.to_attribute_value(), "a=1")

    def test_non_textual_content_types_are_bytes(self):
        for content_type in (
            "application/octet-stream",
            "image/png",
            "multipart/form-data; boundary=x",
            "application/jsonl",
        ):
            with self.subTest(content_type=content_type):
                buffer = BodyBuffer(100, content_type)
                buffer.write(0, b"a=1")
                value = buffer.to_attribute_value()
                self.assertIsInstance(value, bytes)
                self.assertEqual(value, b"a=1")

    def test_missing_content_type_is_bytes(self):
        # An empty header value is treated like a missing one.
        for content_type in (None, ""):
            with self.subTest(content_type=content_type):
                buffer = BodyBuffer(100, content_type)
                buffer.write(0, b"hello")
                value = buffer.to_attribute_value()
                self.assertIsInstance(value, bytes)
                self.assertEqual(value, b"hello")

    def test_charset_parameter_is_used(self):
        for content_type in (
            "text/plain; charset=latin-1",
            'text/plain; CHARSET="latin-1"',
            "text/plain;charset=latin-1;format=flowed",
        ):
            with self.subTest(content_type=content_type):
                buffer = BodyBuffer(100, content_type)
                buffer.write(0, "héllo".encode("latin-1"))
                self.assertEqual(buffer.to_attribute_value(), "héllo")

    def test_unknown_charset_falls_back_to_bytes(self):
        buffer = BodyBuffer(100, "text/plain; charset=not-a-charset")
        buffer.write(0, b"hello")
        self.assertEqual(buffer.to_attribute_value(), b"hello")

    def test_invalid_text_falls_back_to_bytes(self):
        buffer = BodyBuffer(100, "application/json")
        buffer.write(0, b'{"a": "\xff"}')
        self.assertEqual(buffer.to_attribute_value(), b'{"a": "\xff"}')

    def test_truncation_drops_partial_character(self):
        # "é" is two bytes in UTF-8; the limit splits it.
        buffer = BodyBuffer(2, "text/plain")
        buffer.write(0, "aé".encode())
        self.assertEqual(buffer.to_attribute_value(), "a")

    def test_partial_read_drops_partial_character(self):
        buffer = BodyBuffer(100, "text/plain")
        buffer.write(0, "aé".encode()[:2])
        self.assertEqual(buffer.to_attribute_value(), "a")

    def test_truncation_respects_multibyte_charset(self):
        buffer = BodyBuffer(5, "text/plain; charset=utf-16-le")
        buffer.write(0, "abc".encode("utf-16-le"))
        self.assertEqual(buffer.to_attribute_value(), "ab")


class TestCreateBodyBuffer(unittest.TestCase):
    def test_creates_buffer(self):
        self.assertIsInstance(create_body_buffer(10, "text/plain", None), BodyBuffer)
        self.assertIsInstance(create_body_buffer(10, None, ""), BodyBuffer)
        self.assertIsInstance(create_body_buffer(10, None, " Identity "), BodyBuffer)

    def test_no_buffer_for_content_coding(self):
        self.assertIsNone(create_body_buffer(10, "text/plain", "gzip"))
        self.assertIsNone(create_body_buffer(10, "text/plain", "deflate, br"))

    def test_no_buffer_for_non_positive_size(self):
        self.assertIsNone(create_body_buffer(0, "text/plain", None))
        self.assertIsNone(create_body_buffer(-1, "text/plain", None))


class TestCapturingStream(unittest.TestCase):
    def setUp(self):
        self.buffer = BodyBuffer(100, "text/plain")
        self.raw = io.BytesIO(b"line one\nline two\nline three\n")
        self.stream = CapturingStream(self.raw, self.buffer)

    def test_read_returns_underlying_data(self):
        self.assertEqual(self.stream.read(4), b"line")
        self.assertEqual(self.stream.read(), b" one\nline two\nline three\n")
        self.assertEqual(self.buffer.to_attribute_value(), "line one\nline two\nline three\n")

    def test_readline(self):
        self.assertEqual(self.stream.readline(), b"line one\n")
        self.assertEqual(self.stream.readline(4), b"line")
        self.assertEqual(self.buffer.to_attribute_value(), "line one\nline")

    def test_readlines(self):
        self.assertEqual(self.stream.readlines(), [b"line one\n", b"line two\n", b"line three\n"])
        self.assertEqual(self.buffer.to_attribute_value(), "line one\nline two\nline three\n")

    def test_iteration(self):
        self.assertEqual(list(self.stream), [b"line one\n", b"line two\n", b"line three\n"])
        self.assertEqual(self.buffer.to_attribute_value(), "line one\nline two\nline three\n")

    def test_readinto(self):
        target = bytearray(8)
        self.assertEqual(self.stream.readinto(target), 8)
        self.assertEqual(target, b"line one")
        self.assertEqual(self.buffer.to_attribute_value(), "line one")

    def test_seek_and_reread_is_not_duplicated(self):
        self.stream.read(8)
        self.assertEqual(self.stream.seek(0), 0)
        self.stream.read()
        self.assertEqual(self.buffer.to_attribute_value(), "line one\nline two\nline three\n")

    def test_seek_to_end_without_reading(self):
        # Django checks the body size this way before reading it.
        self.stream.seek(0, io.SEEK_END)
        self.stream.seek(0)
        self.stream.read(4)
        self.assertEqual(self.buffer.to_attribute_value(), "line")

    def test_nothing_captured_without_reads(self):
        self.assertIsNone(self.buffer.to_attribute_value())
        self.assertEqual(self.raw.tell(), 0)

    def test_optional_methods_only_present_when_wrapped_stream_has_them(self):
        class ReadOnlyStream:
            def __init__(self):
                self._raw = io.BytesIO(b"body")

            def read(self, *args):
                return self._raw.read(*args)

            def readline(self, *args):
                return self._raw.readline(*args)

            def readlines(self, *args):
                return self._raw.readlines(*args)

            def __iter__(self):
                return iter(self._raw)

        stream = CapturingStream(ReadOnlyStream(), self.buffer)
        self.assertFalse(hasattr(stream, "seek"))
        self.assertFalse(hasattr(stream, "readinto"))
        self.assertTrue(hasattr(self.stream, "seek"))
        self.assertTrue(hasattr(self.stream, "readinto"))
        self.assertEqual(stream.read(), b"body")
        self.assertEqual(self.buffer.to_attribute_value(), "body")

    def test_other_attributes_are_forwarded(self):
        self.assertTrue(self.stream.seekable())
        self.stream.read(4)
        self.assertEqual(self.stream.tell(), 4)
        self.stream.close()
        self.assertTrue(self.raw.closed)

    def test_next(self):
        self.assertEqual(next(self.stream), b"line one\n")
        self.assertEqual(self.buffer.to_attribute_value(), "line one\n")

    def test_iteration_keeps_wrapped_stream_chunks(self):
        class ChunkIterStream:
            def __init__(self):
                self._raw = io.BytesIO(b"hello\nworld\n")

            def read(self, *args):
                return self._raw.read(*args)

            def readline(self, *args):
                return self._raw.readline(*args)

            def __iter__(self):
                return iter(lambda: self._raw.read(4), b"")

        stream = CapturingStream(ChunkIterStream(), self.buffer)
        self.assertEqual(list(stream), [b"hell", b"o\nwo", b"rld\n"])
        self.assertEqual(self.buffer.to_attribute_value(), "hello\nworld\n")

    def test_unknown_method_call_stops_capture(self):
        stream = CapturingStream(io.BufferedReader(io.BytesIO(b"hello\nworld\n")), self.buffer)
        self.assertEqual(stream.read(2), b"he")
        self.assertEqual(stream.read1(3), b"llo")
        self.assertEqual(stream.read(), b"\nworld\n")
        self.assertEqual(self.buffer.to_attribute_value(), "he")

    def test_unknown_method_lookup_keeps_capturing(self):
        stream = CapturingStream(io.BufferedReader(io.BytesIO(b"hello\n")), self.buffer)
        self.assertTrue(hasattr(stream, "read1"))
        self.assertEqual(stream.read(), b"hello\n")
        self.assertEqual(self.buffer.to_attribute_value(), "hello\n")

    def test_non_consuming_methods_keep_capturing(self):
        stream = CapturingStream(io.BufferedReader(io.BytesIO(b"hello\n")), self.buffer)
        self.assertTrue(stream.peek(1).startswith(b"h"))
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(stream.read(), b"hello\n")
        self.assertEqual(self.buffer.to_attribute_value(), "hello\n")

    def test_is_transparent_proxy(self):
        self.assertIsInstance(self.stream, io.BytesIO)
        with self.stream as entered:
            self.assertIs(entered, self.raw)
        self.assertTrue(self.raw.closed)

    def test_attribute_assignment_reaches_wrapped_stream(self):
        self.stream.marker = "set"
        self.assertEqual(vars(self.raw)["marker"], "set")
