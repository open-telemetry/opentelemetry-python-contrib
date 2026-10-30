# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for capturing HTTP bodies as span attributes.

Instrumentation does not itself read the body, so only the bytes read by the
application can be recorded.

This feature is experimental.
"""

from __future__ import annotations

import codecs
import functools
from collections.abc import Callable, Iterator
from typing import Any, BinaryIO, Final

import wrapt

# TODO: use the semconv constant once the semconv package is generated from a
# semantic conventions release that includes this attribute (> 1.44.0).
HTTP_REQUEST_BODY_CONTENT: Final = "http.request.body.content"

_TEXTUAL_SUBTYPE_SUFFIXES = ("/json", "+json", "/xml", "+xml", "/yaml", "+yaml")


def _parse_content_type(content_type: str) -> tuple[str, str | None]:
    """Returns the lowercased type/subtype and the charset parameter, if any."""
    media_type, *params = content_type.split(";")
    charset = None
    for param in params:
        name, _, value = param.partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip('"') or None
    return media_type.strip().lower(), charset


def _is_textual(media_type: str) -> bool:
    return (
        media_type.startswith("text/")
        or media_type.endswith(_TEXTUAL_SUBTYPE_SUFFIXES)
        or media_type == "application/x-www-form-urlencoded"
    )


class BodyBuffer:
    """Holds up to ``max_size`` bytes of a body, indexed by stream position.

    Writes are keyed by the position the bytes were read from, so a body that
    is seeked back and read again is not recorded twice.
    """

    def __init__(self, max_size: int, content_type: str | None):
        self._max_size = max_size
        self._content_type = content_type
        self._data = bytearray()

    def write(self, position: int, data: bytes | bytearray | memoryview) -> None:
        if position > len(self._data):
            # Bytes before this position were skipped by the application, so
            # the captured prefix cannot be extended contiguously.
            return
        end = min(position + len(data), self._max_size)
        self._data[position:end] = data[: end - position]

    def to_attribute_value(self) -> str | bytes | None:
        """Returns the captured body as a string when it is text, else bytes.

        Returns ``None`` when nothing was captured.
        """
        if not self._data:
            return None
        data = bytes(self._data)
        if self._content_type is None:
            return data
        media_type, charset = _parse_content_type(self._content_type)
        if charset is None:
            if not _is_textual(media_type):
                return data
            charset = "utf-8"
        try:
            decoder = codecs.getincrementaldecoder(charset)(errors="strict")
            # The captured bytes may end in the middle of a character, because
            # of the size limit or because the application stopped reading.
            # final=False drops that partial character so the value is valid.
            return decoder.decode(data, final=False)
        except (LookupError, UnicodeDecodeError):
            return data


def create_body_buffer(
    max_size: int,
    content_type: str | None,
    content_encoding: str | None,
) -> BodyBuffer | None:
    """Returns a buffer for a body, or ``None`` if it should not be captured.

    Bodies with a content coding are not captured.
    """
    if max_size <= 0:
        return None
    if content_encoding and content_encoding.strip().lower() != "identity":
        return None
    return BodyBuffer(max_size, content_type)


# Stream methods that do not move the stream position.
_NON_CONSUMING_METHODS = frozenset(
    {"close", "fileno", "flush", "isatty", "peek", "readable", "seekable", "tell", "writable"}
)


class CapturingStream(wrapt.ObjectProxy):
    """Proxies a binary input stream, copying what the application reads.

    Reads through the PEP-defined WSGI input stream methods, iteration, ``readinto`` and ``seek``
    are captured. Calling any other method that is not known to leave the stream position alone
    stops capture, since it may consume bytes the proxy cannot see.
    """

    def __init__(self, stream: BinaryIO, buffer: BodyBuffer):
        super().__init__(stream)
        self._self_buffer = buffer
        self._self_position: int | None = 0

    def _self_capture(self, data: bytes | bytearray | memoryview) -> None:
        if self._self_position is None:
            return
        self._self_buffer.write(self._self_position, data)
        self._self_position += len(data)

    def read(self, *args: Any) -> bytes:
        data = self.__wrapped__.read(*args)
        self._self_capture(data)
        return data

    def readline(self, *args: Any) -> bytes:
        data = self.__wrapped__.readline(*args)
        self._self_capture(data)
        return data

    def readlines(self, *args: Any) -> list[bytes]:
        lines = self.__wrapped__.readlines(*args)
        for line in lines:
            self._self_capture(line)
        return lines

    def __iter__(self) -> Iterator[bytes]:
        for data in self.__wrapped__:
            self._self_capture(data)
            yield data

    def __next__(self) -> bytes:
        data = next(self.__wrapped__)
        self._self_capture(data)
        return data

    def _self_readinto(self, target: bytearray | memoryview) -> int | None:
        count = self.__wrapped__.readinto(target)
        if count:
            self._self_capture(memoryview(target)[:count])
        return count

    def _self_seek(self, *args: Any) -> int:
        position = self.__wrapped__.seek(*args)
        # Without a known position, further reads cannot be placed in the
        # buffer, so stop capturing instead of corrupting it.
        self._self_position = position if isinstance(position, int) else None
        return position

    def _self_stop_capture_on_call(self, method: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(method)
        def call(*args: Any, **kwargs: Any) -> Any:
            self._self_position = None
            return method(*args, **kwargs)

        return call

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self.__wrapped__, name)
        # Non-PEP, but commonly used WSGI methods. We don't define them on the class
        # itself so they can be queried with hasattr.
        if name == "readinto":
            return self._self_readinto
        if name == "seek":
            return self._self_seek
        if name in _NON_CONSUMING_METHODS or not callable(attribute):
            return attribute
        return self._self_stop_capture_on_call(attribute)
