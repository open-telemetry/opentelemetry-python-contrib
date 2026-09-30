# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence

_REDACTED = "[REDACTED]"


def get_header_value(headers: Mapping[str, str | Sequence[str]] | None, name: str) -> str | None:
    """Return the first non-empty value of header ``name``.

    ``name`` must be lowercase; ``headers`` must have lowercase names or be a case-insensitive mapping.
    """
    if not headers:
        return None
    value = headers.get(name)
    if value is None or isinstance(value, str):
        return value or None
    return next((item for item in value if item), None)


class _HeaderNameMatcher:
    """Matches lowercased header names.

    Compiled regular expressions must fully match the lowercased header name;
    strings must equal the header name case-insensitively.
    """

    def __init__(self, patterns: Collection[str | re.Pattern[str]] | None) -> None:
        patterns = patterns or ()
        self._names = frozenset(pattern.lower() for pattern in patterns if isinstance(pattern, str))
        self._patterns = tuple(pattern for pattern in patterns if isinstance(pattern, re.Pattern))

    def __bool__(self) -> bool:
        return bool(self._names or self._patterns)

    def matches(self, lowered_name: str) -> bool:
        return lowered_name in self._names or any(pattern.fullmatch(lowered_name) for pattern in self._patterns)


class HeaderCapture:
    """Builds the captured header span attributes for request or response headers."""

    def __init__(
        self,
        *,
        attribute_prefix: str,
        captured: Collection[str | re.Pattern[str]] | None,
        sanitized: Collection[str | re.Pattern[str]] | None,
    ) -> None:
        self._attribute_prefix = attribute_prefix
        self._captured = _HeaderNameMatcher(captured)
        self._sanitized = _HeaderNameMatcher(sanitized)

    def get_attributes(self, headers: Mapping[str, str | Sequence[str]] | None) -> dict[str, tuple[str, ...]]:
        """Return the ``<prefix>.<lowercased name>`` attributes of the captured headers."""
        if not self._captured or not headers:
            return {}
        attributes: dict[str, tuple[str, ...]] = {}
        for name, value in headers.items():
            lowered_name = name.lower()
            if not self._captured.matches(lowered_name):
                continue
            values = (value,) if isinstance(value, str) else tuple(value)
            if self._sanitized.matches(lowered_name):
                values = (_REDACTED,) * len(values)
            key = f"{self._attribute_prefix}.{lowered_name}"
            attributes[key] = attributes.get(key, ()) + values
        return attributes
