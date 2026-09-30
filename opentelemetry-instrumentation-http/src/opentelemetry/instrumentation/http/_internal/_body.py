# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import codecs
from email.message import Message

_DEFAULT_CHARSET = "utf-8"
CONTENT_TYPE_HEADER = "content-type"
_TEXTUAL_TYPE_PREFIXES = ("text/",)
_TEXTUAL_TYPE_SUFFIXES = ("/json", "+json", "/xml", "+xml", "/yaml", "+yaml")
_TEXTUAL_TYPES = frozenset({"application/x-www-form-urlencoded"})


def _get_media_type(content_type: str) -> str:
    return content_type.partition(";")[0].strip().lower()


def _get_charset_parameter(content_type: str) -> str | None:
    message = Message()
    message[CONTENT_TYPE_HEADER] = content_type
    return message.get_content_charset() or None


def is_textual_content_type(content_type: str | None) -> bool:
    """Return whether ``content_type`` indicates textual content, per the HTTP semantic conventions."""
    if not content_type:
        return False
    media_type = _get_media_type(content_type)
    return (
        media_type.startswith(_TEXTUAL_TYPE_PREFIXES)
        or media_type.endswith(_TEXTUAL_TYPE_SUFFIXES)
        or media_type in _TEXTUAL_TYPES
        or _get_charset_parameter(content_type) is not None
    )


def get_charset(content_type: str | None) -> str:
    """Return the ``charset`` of ``content_type``, or UTF-8 when it is missing or unknown."""
    if not content_type:
        return _DEFAULT_CHARSET
    charset = _get_charset_parameter(content_type)
    if charset is None:
        return _DEFAULT_CHARSET
    try:
        codecs.lookup(charset)
    except LookupError:
        return _DEFAULT_CHARSET
    return charset


class BodyContentCapture:
    """Buffers body content chunks up to a maximum size in bytes."""

    def __init__(self, max_size: int | None) -> None:
        self._max_size = max_size if max_size is not None and max_size > 0 else None
        self._buffer = bytearray()
        self._added = False
        self._truncated = False

    def add(self, chunk: bytes) -> None:
        """Append ``chunk``, truncating the content once the maximum size is reached."""
        self._added = True
        if self._truncated:
            return
        if self._max_size is not None and len(self._buffer) + len(chunk) > self._max_size:
            self._buffer += chunk[: self._max_size - len(self._buffer)]
            self._truncated = True
            return
        self._buffer += chunk

    def get_content(self, content_type: str | None) -> str | None:
        """Return the buffered content decoded as text, or ``None`` if none was added or it is not textual.

        Truncated content is cut on a character boundary. Invalid bytes are replaced.
        """
        if not self._added or not is_textual_content_type(content_type):
            return None
        decoder = codecs.getincrementaldecoder(get_charset(content_type))(errors="replace")
        return decoder.decode(bytes(self._buffer), final=not self._truncated)
