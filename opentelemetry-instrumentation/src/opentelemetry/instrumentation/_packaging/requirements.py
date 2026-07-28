# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""A minimal PEP 508 requirement implementation.

This provides the subset of :mod:`packaging.requirements` that OpenTelemetry
instrumentation relies on: parsing a requirement string such as
``flask >= 2.2.0; extra == "instruments"`` into its ``name``, ``specifier`` and
``marker`` components.
"""

from __future__ import annotations

from re import compile as re_compile
from typing import Optional, Set

from opentelemetry.instrumentation._packaging.markers import (
    InvalidMarker,
    Marker,
)
from opentelemetry.instrumentation._packaging.specifiers import (
    InvalidSpecifier,
    SpecifierSet,
)

__all__ = ["InvalidRequirement", "Requirement"]

# PEP 508 project name: alphanumerics separated by ``.``, ``-`` or ``_``.
_NAME_REGEX = re_compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)",
)


class InvalidRequirement(ValueError):
    """Raised when a requirement string does not conform to PEP 508."""


class Requirement:
    def __init__(self, requirement_string: str) -> None:
        marker_string: Optional[str] = None
        remainder = requirement_string
        if ";" in remainder:
            remainder, marker_string = remainder.split(";", 1)

        remainder = remainder.strip()
        name_match = _NAME_REGEX.match(remainder)
        if name_match is None:
            raise InvalidRequirement(
                f"Invalid requirement: {requirement_string!r}"
            )

        self.name: str = name_match.group(1)
        remainder = remainder[name_match.end() :].strip()

        self.extras: Set[str] = set()
        if remainder.startswith("["):
            end = remainder.find("]")
            if end == -1:
                raise InvalidRequirement(
                    f"Invalid requirement: {requirement_string!r}"
                )
            self.extras = {
                extra.strip()
                for extra in remainder[1:end].split(",")
                if extra.strip()
            }
            remainder = remainder[end + 1 :].strip()

        self.url: Optional[str] = None
        if remainder.startswith("@"):
            self.url = remainder[1:].strip()
            remainder = ""

        try:
            self.specifier: SpecifierSet = SpecifierSet(remainder)
        except InvalidSpecifier as exc:
            raise InvalidRequirement(
                f"Invalid requirement: {requirement_string!r}"
            ) from exc

        self.marker: Optional[Marker] = None
        if marker_string is not None and marker_string.strip():
            try:
                self.marker = Marker(marker_string)
            except InvalidMarker as exc:
                raise InvalidRequirement(
                    f"Invalid requirement: {requirement_string!r}"
                ) from exc

    def __str__(self) -> str:
        parts = [self.name]
        if self.extras:
            parts.append(f"[{','.join(sorted(self.extras))}]")
        if len(self.specifier):
            parts.append(str(self.specifier))
        if self.url:
            parts.append(f"@ {self.url}")
            if self.marker:
                parts.append(" ")
        if self.marker:
            parts.append(f"; {self.marker}")
        return "".join(parts)

    def __repr__(self) -> str:
        return f"<Requirement('{self}')>"
