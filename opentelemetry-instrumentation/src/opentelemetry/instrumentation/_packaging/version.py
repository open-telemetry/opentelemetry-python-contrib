# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""A minimal PEP 440 version implementation.

This provides the subset of :mod:`packaging.version` that OpenTelemetry
instrumentation relies on: parsing, normalization and ordering of PEP 440
versions, the ``release`` tuple and the pre/post/dev release predicates used
by the specifier logic. It intentionally does not implement legacy (non
PEP 440) versions, which ``packaging`` dropped support for.
"""

from __future__ import annotations

from functools import total_ordering
from itertools import dropwhile
from re import IGNORECASE, VERBOSE
from re import compile as re_compile
from typing import NamedTuple, Optional, Tuple, Union

__all__ = ["InvalidVersion", "Version", "parse"]


class InvalidVersion(ValueError):
    """Raised when a version string is not a valid PEP 440 version."""


class _InfinityType:
    def __repr__(self) -> str:
        return "Infinity"

    def __lt__(self, other: object) -> bool:
        return False

    def __le__(self, other: object) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self))

    def __gt__(self, other: object) -> bool:
        return True

    def __ge__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash(repr(self))


_Infinity = _InfinityType()


class _NegativeInfinityType:
    def __repr__(self) -> str:
        return "-Infinity"

    def __lt__(self, other: object) -> bool:
        return True

    def __le__(self, other: object) -> bool:
        return True

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self))

    def __gt__(self, other: object) -> bool:
        return False

    def __ge__(self, other: object) -> bool:
        return False

    def __hash__(self) -> int:
        return hash(repr(self))


_NegativeInfinity = _NegativeInfinityType()

# A single pre/post/dev segment is a ("a"/"b"/"rc"/"post"/"dev", int) pair.
_LetterVersion = Tuple[str, int]
_LocalSegment = Union[int, str]
_LocalVersion = Optional[Tuple[_LocalSegment, ...]]


class _Parsed(NamedTuple):
    epoch: int
    release: Tuple[int, ...]
    pre: Optional[_LetterVersion]
    post: Optional[_LetterVersion]
    dev: Optional[_LetterVersion]
    local: _LocalVersion


# Comparison key element types: after normalization each of the pre/post/dev
# fields collapses to a comparable value that may be an infinity sentinel.
_CmpPrePostDev = Union[_InfinityType, _NegativeInfinityType, _LetterVersion]
_CmpLocal = Union[
    _NegativeInfinityType,
    Tuple[Union[Tuple[int, str], Tuple[_NegativeInfinityType, str]], ...],
]
_CmpKey = Tuple[
    int,
    Tuple[int, ...],
    _CmpPrePostDev,
    _CmpPrePostDev,
    _CmpPrePostDev,
    _CmpLocal,
]

# The canonical PEP 440 version pattern.
_VERSION_PATTERN = r"""
    v?
    (?:
        (?:(?P<epoch>[0-9]+)!)?                           # epoch
        (?P<release>[0-9]+(?:\.[0-9]+)*)                  # release segment
        (?P<pre>                                          # pre-release
            [-_\.]?
            (?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)
            [-_\.]?
            (?P<pre_n>[0-9]+)?
        )?
        (?P<post>                                         # post release
            (?:-(?P<post_n1>[0-9]+))
            |
            (?:
                [-_\.]?
                (?P<post_l>post|rev|r)
                [-_\.]?
                (?P<post_n2>[0-9]+)?
            )
        )?
        (?P<dev>                                          # dev release
            [-_\.]?
            (?P<dev_l>dev)
            [-_\.]?
            (?P<dev_n>[0-9]+)?
        )?
    )
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?       # local version
"""

_VERSION_REGEX = re_compile(
    r"^\s*" + _VERSION_PATTERN + r"\s*$",
    VERBOSE | IGNORECASE,
)

_LOCAL_SEGMENT_SPLIT = re_compile(r"[\._-]")


def _parse_letter_version(
    letter: Optional[str], number: Optional[str]
) -> Optional[_LetterVersion]:
    if letter:
        # A pre-release without an explicit number implies 0.
        normalized = letter.lower()
        if normalized == "alpha":
            normalized = "a"
        elif normalized == "beta":
            normalized = "b"
        elif normalized in ("c", "pre", "preview"):
            normalized = "rc"
        elif normalized in ("rev", "r"):
            normalized = "post"
        return normalized, int(number) if number else 0

    if number:
        # An implicit post release, e.g. the "-1" in "1.0-1".
        return "post", int(number)

    return None


def _parse_local_version(local: Optional[str]) -> _LocalVersion:
    if local is None:
        return None
    return tuple(
        part.lower() if not part.isdigit() else int(part)
        for part in _LOCAL_SEGMENT_SPLIT.split(local)
    )


def _build_cmp_key(parsed: _Parsed) -> _CmpKey:
    # Trailing zeros in the release segment are not significant for ordering,
    # e.g. 1.0 == 1.0.0.
    release = tuple(
        reversed(list(dropwhile(lambda x: x == 0, reversed(parsed.release))))
    )

    # A version with no pre-segment sorts after one that has a pre-segment,
    # unless it is a dev release with neither pre nor post, which sorts first.
    if parsed.pre is None and parsed.post is None and parsed.dev is not None:
        pre: _CmpPrePostDev = _NegativeInfinity
    elif parsed.pre is None:
        pre = _Infinity
    else:
        pre = parsed.pre

    post: _CmpPrePostDev = (
        _NegativeInfinity if parsed.post is None else parsed.post
    )
    dev: _CmpPrePostDev = _Infinity if parsed.dev is None else parsed.dev

    if parsed.local is None:
        # No local version sorts before any local version.
        local: _CmpLocal = _NegativeInfinity
    else:
        # Per PEP 440, numeric local segments sort after alphabetic ones.
        local = tuple(
            (segment, "")
            if isinstance(segment, int)
            else (_NegativeInfinity, segment)
            for segment in parsed.local
        )

    return parsed.epoch, release, pre, post, dev, local


@total_ordering
class Version:
    """A PEP 440 version, orderable and hashable."""

    def __init__(self, version: str) -> None:
        match = _VERSION_REGEX.match(version)
        if match is None:
            raise InvalidVersion(f"Invalid version: '{version}'")

        self._parsed = _Parsed(
            epoch=int(match.group("epoch")) if match.group("epoch") else 0,
            release=tuple(
                int(part) for part in match.group("release").split(".")
            ),
            pre=_parse_letter_version(
                match.group("pre_l"), match.group("pre_n")
            ),
            post=_parse_letter_version(
                match.group("post_l"),
                match.group("post_n1") or match.group("post_n2"),
            ),
            dev=_parse_letter_version(
                match.group("dev_l"), match.group("dev_n")
            ),
            local=_parse_local_version(match.group("local")),
        )
        self._key = _build_cmp_key(self._parsed)

    @property
    def epoch(self) -> int:
        return self._parsed.epoch

    @property
    def release(self) -> Tuple[int, ...]:
        return self._parsed.release

    @property
    def pre(self) -> Optional[_LetterVersion]:
        return self._parsed.pre

    @property
    def post(self) -> Optional[int]:
        return self._parsed.post[1] if self._parsed.post else None

    @property
    def dev(self) -> Optional[int]:
        return self._parsed.dev[1] if self._parsed.dev else None

    @property
    def local(self) -> Optional[str]:
        if self._parsed.local is None:
            return None
        return ".".join(str(segment) for segment in self._parsed.local)

    @property
    def is_prerelease(self) -> bool:
        return self._parsed.pre is not None or self._parsed.dev is not None

    @property
    def is_postrelease(self) -> bool:
        return self._parsed.post is not None

    @property
    def is_devrelease(self) -> bool:
        return self._parsed.dev is not None

    @property
    def base_version(self) -> str:
        parts = []
        if self.epoch != 0:
            parts.append(f"{self.epoch}!")
        parts.append(".".join(str(part) for part in self.release))
        return "".join(parts)

    @property
    def public(self) -> str:
        """The version string without its local segment."""
        return str(self).split("+", 1)[0]

    def __str__(self) -> str:
        parts = [self.base_version]
        if self._parsed.pre is not None:
            parts.append("".join(str(item) for item in self._parsed.pre))
        if self._parsed.post is not None:
            parts.append(f".post{self._parsed.post[1]}")
        if self._parsed.dev is not None:
            parts.append(f".dev{self._parsed.dev[1]}")
        if self.local is not None:
            parts.append(f"+{self.local}")
        return "".join(parts)

    def __repr__(self) -> str:
        return f"<Version('{self}')>"

    def __hash__(self) -> int:
        return hash(self._key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key == other._key

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key < other._key


def parse(version: str) -> Version:
    """Parse ``version`` into a :class:`Version`, raising :class:`InvalidVersion`."""
    return Version(version)
