# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""A minimal PEP 440 version specifier implementation.

This provides the subset of :mod:`packaging.specifiers` that OpenTelemetry
instrumentation relies on: parsing a specifier set such as ``>=1.0,<2.0`` and
testing whether a version satisfies it via :meth:`SpecifierSet.contains` and
:meth:`SpecifierSet.filter`, including the PEP 440 pre-release matching rules.
"""

from __future__ import annotations

from itertools import takewhile
from typing import Iterable, Iterator, List, Optional, Tuple, Union

from opentelemetry.instrumentation._packaging.version import (
    InvalidVersion,
    Version,
)

__all__ = ["InvalidSpecifier", "Specifier", "SpecifierSet"]

_OPERATORS = ("===", "~=", "==", "!=", "<=", ">=", "<", ">")


class InvalidSpecifier(ValueError):
    """Raised when a specifier string does not conform to PEP 440."""


def _coerce_version(item: Union[str, Version]) -> Optional[Version]:
    if isinstance(item, Version):
        return item
    try:
        return Version(item)
    except InvalidVersion:
        return None


def _canonical_public(item: Union[str, Version]) -> str:
    """Normalize ``item`` to its public (local-less) version string."""
    version = item if isinstance(item, Version) else Version(item)
    return version.public


def _version_split(version: str) -> List[str]:
    result: List[str] = []
    epoch, _, rest = version.rpartition("!")
    result.append(epoch or "0")
    for item in rest.split("."):
        # Split a trailing pre-release attached to a numeric segment, e.g. the
        # "1a1" in "1.1a1" becomes the two components "1" and "a1".
        index = len(item)
        for pos, char in enumerate(item):
            if char in "abcr":
                index = pos
                break
        if 0 < index < len(item):
            result.append(item[:index])
            result.append(item[index:])
        else:
            result.append(item)
    return result


def _version_join(components: List[str]) -> str:
    epoch, *rest = components
    return f"{epoch}!{'.'.join(rest)}"


def _is_not_suffix(segment: str) -> bool:
    return not any(segment.startswith(prefix) for prefix in ("dev", "a", "b", "rc", "post"))


def _numeric_prefix_len(split: List[str]) -> int:
    count = 0
    for segment in split:
        if not segment.isdigit():
            break
        count += 1
    return count


def _left_pad(split: List[str], target_numeric_len: int) -> List[str]:
    numeric_len = _numeric_prefix_len(split)
    pad_needed = target_numeric_len - numeric_len
    if pad_needed <= 0:
        return split
    return [
        *split[:numeric_len],
        *(["0"] * pad_needed),
        *split[numeric_len:],
    ]


def _earliest_prerelease(version: Version) -> Version:
    parts = [version.base_version]
    if version.pre is not None:
        parts.append(f"{version.pre[0]}{version.pre[1]}")
    if version.is_postrelease:
        parts.append(f".post{version.post}")
    parts.append(".dev0")
    return Version("".join(parts))


def _post_base(version: Version) -> Version:
    parts = [version.base_version]
    if version.pre is not None:
        parts.append(f"{version.pre[0]}{version.pre[1]}")
    return Version("".join(parts))


class Specifier:
    """A single PEP 440 specifier, e.g. ``>=1.0`` or ``==1.4.*``."""

    def __init__(self, spec: str = "", prereleases: Optional[bool] = None) -> None:
        spec = spec.strip()
        operator = ""
        for candidate in _OPERATORS:
            if spec.startswith(candidate):
                operator = candidate
                break
        if not operator:
            raise InvalidSpecifier(f"Invalid specifier: {spec!r}")

        version = spec[len(operator) :].strip()
        if not version:
            raise InvalidSpecifier(f"Invalid specifier: {spec!r}")

        if operator != "===":
            wildcard = version.endswith(".*")
            if wildcard and operator not in ("==", "!="):
                raise InvalidSpecifier(f"Invalid specifier: {spec!r}")
            base = version[:-2] if wildcard else version
            try:
                parsed = Version(base)
            except InvalidVersion as exc:
                raise InvalidSpecifier(f"Invalid specifier: {spec!r}") from exc
            if wildcard and (
                parsed.pre is not None or parsed.is_postrelease or parsed.is_devrelease or parsed.local is not None
            ):
                raise InvalidSpecifier(f"Invalid specifier: {spec!r}")
            if operator == "~=" and len(parsed.release) < 2:
                raise InvalidSpecifier(f"Invalid specifier: {spec!r}")

        self._spec: Tuple[str, str] = (operator, version)
        self._prereleases = prereleases

    @property
    def operator(self) -> str:
        return self._spec[0]

    @property
    def version(self) -> str:
        return self._spec[1]

    @property
    def prereleases(self) -> Optional[bool]:
        if self._prereleases is not None:
            return self._prereleases
        operator, version = self._spec
        if operator == "!=":
            return False
        if operator == "==" and version.endswith(".*"):
            return False
        if operator == "===":
            return None
        return Version(version).is_prerelease

    @prereleases.setter
    def prereleases(self, value: bool) -> None:
        self._prereleases = value

    def __str__(self) -> str:
        return f"{self._spec[0]}{self._spec[1]}"

    def __repr__(self) -> str:
        return f"<Specifier('{self}')>"

    def __hash__(self) -> int:
        return hash(self._spec)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            try:
                other = Specifier(other)
            except InvalidSpecifier:
                return NotImplemented
        elif not isinstance(other, Specifier):
            return NotImplemented
        return self._spec == other._spec

    def _compare_compatible(self, prospective: Version, spec: str) -> bool:
        prefix = _version_join(list(takewhile(_is_not_suffix, _version_split(spec)))[:-1])
        prefix += ".*"
        return self._compare_greater_than_equal(prospective, spec) and self._compare_equal(prospective, prefix)

    @staticmethod
    def _compare_equal(prospective: Version, spec: str) -> bool:
        if spec.endswith(".*"):
            normalized_spec = _canonical_public(spec[:-2])
            split_spec = _version_split(normalized_spec)
            spec_numeric_len = _numeric_prefix_len(split_spec)

            normalized_prospective = _canonical_public(prospective)
            split_prospective = _version_split(normalized_prospective)
            padded_prospective = _left_pad(split_prospective, spec_numeric_len)
            shortened_prospective = padded_prospective[: len(split_spec)]
            return shortened_prospective == split_spec

        spec_version = Version(spec)
        if not spec_version.local:
            prospective = Version(prospective.public)
        return prospective == spec_version

    def _compare_not_equal(self, prospective: Version, spec: str) -> bool:
        return not self._compare_equal(prospective, spec)

    @staticmethod
    def _compare_less_than_equal(prospective: Version, spec: str) -> bool:
        return Version(prospective.public) <= Version(spec)

    @staticmethod
    def _compare_greater_than_equal(prospective: Version, spec: str) -> bool:
        return Version(prospective.public) >= Version(spec)

    @staticmethod
    def _compare_less_than(prospective: Version, spec_str: str) -> bool:
        spec = Version(spec_str)
        if not prospective < spec:
            return False
        if not spec.is_prerelease and prospective.is_prerelease and prospective >= _earliest_prerelease(spec):
            return False
        return True

    @staticmethod
    def _compare_greater_than(prospective: Version, spec_str: str) -> bool:
        spec = Version(spec_str)
        if not prospective > spec:
            return False
        if not spec.is_postrelease and prospective.is_postrelease and _post_base(prospective) == spec:
            return False
        if prospective.local is not None and Version(prospective.public) == spec:
            return False
        return True

    @staticmethod
    def _compare_arbitrary(prospective: Union[Version, str], spec: str) -> bool:
        return str(prospective).lower() == str(spec).lower()

    def _operator_callable(self, prospective: Version, spec: str) -> bool:
        return {
            "~=": self._compare_compatible,
            "==": self._compare_equal,
            "!=": self._compare_not_equal,
            "<=": self._compare_less_than_equal,
            ">=": self._compare_greater_than_equal,
            "<": self._compare_less_than,
            ">": self._compare_greater_than,
        }[self.operator](prospective, spec)

    def contains(self, item: Union[str, Version], prereleases: Optional[bool] = None) -> bool:
        return bool(list(self.filter([item], prereleases=prereleases)))

    def filter(
        self,
        iterable: Iterable[Union[str, Version]],
        prereleases: Optional[bool] = None,
    ) -> Iterator[Union[str, Version]]:
        found_prereleases: List[Union[str, Version]] = []
        found_non_prereleases = False
        include_prereleases = prereleases if prereleases is not None else self.prereleases

        for version in iterable:
            parsed_version = _coerce_version(version)
            if parsed_version is None:
                if self.operator == "===" and self._compare_arbitrary(version, self.version):
                    yield version
                continue
            if self.operator == "===":
                if self._compare_arbitrary(version, self.version):
                    found_non_prereleases = True
                    yield version
                continue

            if self._operator_callable(parsed_version, self.version):
                if not parsed_version.is_prerelease or include_prereleases:
                    found_non_prereleases = True
                    yield version
                elif prereleases is None and self._prereleases is not False:
                    found_prereleases.append(version)

        if not found_non_prereleases and prereleases is None and self._prereleases is not False:
            yield from found_prereleases


class SpecifierSet:
    """A comma-separated set of :class:`Specifier` instances, ANDed together."""

    def __init__(self, specifiers: str = "", prereleases: Optional[bool] = None) -> None:
        split = [s.strip() for s in specifiers.split(",") if s.strip()]
        self._specs: Tuple[Specifier, ...] = tuple(Specifier(spec) for spec in split)
        self._has_arbitrary = "===" in specifiers
        self._prereleases = prereleases

    @property
    def prereleases(self) -> Optional[bool]:
        if self._prereleases is not None:
            return self._prereleases
        if not self._specs:
            return None
        if any(spec.prereleases for spec in self._specs):
            return True
        return None

    @prereleases.setter
    def prereleases(self, value: bool) -> None:
        self._prereleases = value

    def __iter__(self) -> Iterator[Specifier]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)

    def __str__(self) -> str:
        return ",".join(sorted(str(spec) for spec in self._specs))

    def __repr__(self) -> str:
        return f"<SpecifierSet('{self}')>"

    def __hash__(self) -> int:
        return hash(frozenset(self._specs))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            other = SpecifierSet(other)
        elif not isinstance(other, SpecifierSet):
            return NotImplemented
        return frozenset(self._specs) == frozenset(other._specs)

    def contains(
        self,
        item: Union[str, Version],
        prereleases: Optional[bool] = None,
        installed: Optional[bool] = None,
    ) -> bool:
        version = _coerce_version(item)
        if version is not None and installed and version.is_prerelease:
            prereleases = True
        if version is None or (self._has_arbitrary and not isinstance(item, Version)):
            check_item: Union[str, Version] = item
        else:
            check_item = version
        return bool(list(self.filter([check_item], prereleases=prereleases)))

    def filter(
        self,
        iterable: Iterable[Union[str, Version]],
        prereleases: Optional[bool] = None,
    ) -> Iterator[Union[str, Version]]:
        if prereleases is None and self.prereleases is not None:
            prereleases = self.prereleases

        if self._specs:
            result: Iterable[Union[str, Version]] = iterable
            for spec in self._specs:
                result = spec.filter(
                    result,
                    prereleases=True if prereleases is None else prereleases,
                )
            result = list(result)
            if prereleases is not None:
                return iter(result)
            return self._prefer_final_releases(result)

        if prereleases is True:
            return iter(iterable)
        if prereleases is False:
            return iter(
                item for item in iterable if ((version := _coerce_version(item)) is None or not version.is_prerelease)
            )
        return self._prefer_final_releases(iterable)

    @staticmethod
    def _prefer_final_releases(
        iterable: Iterable[Union[str, Version]],
    ) -> Iterator[Union[str, Version]]:
        # PEP 440: exclude prereleases unless no final releases exist. Items
        # that are not valid versions have already passed all specifiers, so
        # they are always kept (their order relative to finals is preserved).
        all_nonfinal: List[Union[str, Version]] = []
        arbitrary_strings: List[Union[str, Version]] = []
        found_final = False
        for item in iterable:
            parsed = _coerce_version(item)
            if parsed is None:
                if found_final:
                    yield item
                else:
                    arbitrary_strings.append(item)
                    all_nonfinal.append(item)
                continue
            if not parsed.is_prerelease:
                if not found_final:
                    yield from arbitrary_strings
                    found_final = True
                yield item
                continue
            if not found_final:
                all_nonfinal.append(item)
        if not found_final:
            yield from all_nonfinal
