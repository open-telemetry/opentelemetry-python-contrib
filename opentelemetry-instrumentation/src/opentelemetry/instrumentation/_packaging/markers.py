# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""A minimal PEP 508 environment marker implementation.

This provides the subset of :mod:`packaging.markers` that OpenTelemetry
instrumentation relies on: parsing a marker expression such as
``extra == "instruments"`` (optionally combined with ``and``/``or`` and other
environment markers) and evaluating it against an environment.
"""

from __future__ import annotations

from operator import eq, ne
from os import name as os_name
from platform import (
    machine,
    python_implementation,
    python_version,
    python_version_tuple,
    release,
    system,
)
from platform import (
    version as platform_version,
)
from sys import implementation
from sys import platform as sys_platform
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from opentelemetry.instrumentation._packaging.specifiers import (
    InvalidSpecifier,
    Specifier,
)

__all__ = [
    "InvalidMarker",
    "Marker",
    "UndefinedComparison",
    "UndefinedEnvironmentName",
    "default_environment",
]


class InvalidMarker(ValueError):
    """Raised when a marker string does not conform to PEP 508."""


class UndefinedComparison(ValueError):
    """Raised when a marker uses a comparison that is undefined for its values."""


class UndefinedEnvironmentName(ValueError):
    """Raised when a marker references a value missing from the environment."""


_VARIABLES = frozenset(
    {
        "implementation_name",
        "implementation_version",
        "os_name",
        "platform_machine",
        "platform_release",
        "platform_system",
        "platform_version",
        "python_full_version",
        "platform_python_implementation",
        "python_version",
        "sys_platform",
        "extra",
    }
)

_MARKERS_REQUIRING_VERSION = frozenset(
    {
        "python_full_version",
        "platform_release",
        "implementation_version",
        "python_version",
    }
)

# The PyPA Dependency Specifiers spec (which supersedes PEP 508) directs
# tools to "treat >= and <= as equivalent to == and treat > and < as always
# being False" for ordered comparisons on string marker fields. This mirrors
# packaging.markers._operators. (PEP 508's older wording instead fell back to
# Python string comparison for these operators.)
_STRING_OPERATORS: Dict[str, Callable[[str, Any], bool]] = {
    "in": lambda lhs, rhs: lhs in rhs,
    "not in": lambda lhs, rhs: lhs not in rhs,
    "<": lambda lhs, rhs: False,
    "<=": eq,
    "==": eq,
    "!=": ne,
    ">=": eq,
    ">": lambda lhs, rhs: False,
}

# Comparison/boolean operators recognized by the tokenizer, longest first.
_OPERATORS = ("===", "~=", "==", "!=", "<=", ">=", "<", ">")

# A parsed marker node is either a comparison tuple, or an ("and"/"or", [nodes]).
_Value = Tuple[str, str]  # ("var", name) or ("str", literal)
_Comparison = Tuple[str, _Value, str, _Value]  # ("cmp", lhs, op, rhs)
_Node = Union[_Comparison, Tuple[str, List["_Node"]]]


def canonicalize_name(name: str) -> str:
    """Normalize a project/extra name per PEP 503."""
    value = name.lower().replace("_", "-").replace(".", "-")
    while "--" in value:
        value = value.replace("--", "-")
    return value


def _format_full_version(info: Any) -> str:
    version = f"{info.major}.{info.minor}.{info.micro}"
    kind = info.releaselevel
    if kind != "final":
        version += kind[0] + str(info.serial)
    return version


def default_environment() -> Dict[str, str]:
    """Return the default marker environment for the current Python process."""
    return {
        "implementation_name": implementation.name,
        "implementation_version": _format_full_version(implementation.version),
        "os_name": os_name,
        "platform_machine": machine(),
        "platform_release": release(),
        "platform_system": system(),
        "platform_version": platform_version(),
        "python_full_version": python_version(),
        "platform_python_implementation": python_implementation(),
        "python_version": ".".join(python_version_tuple()[:2]),
        "sys_platform": sys_platform,
    }


def _tokenize(marker: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    index = 0
    length = len(marker)
    while index < length:
        char = marker[index]
        if char.isspace():
            index += 1
            continue
        if char in ("(", ")"):
            kind = "LPAREN" if char == "(" else "RPAREN"
            tokens.append((kind, char))
            index += 1
            continue
        if char in ("'", '"'):
            end = marker.find(char, index + 1)
            if end == -1:
                raise InvalidMarker(f"Unterminated string in marker: {marker!r}")
            tokens.append(("STR", marker[index + 1 : end]))
            index = end + 1
            continue
        matched_operator = next((op for op in _OPERATORS if marker.startswith(op, index)), None)
        if matched_operator is not None:
            tokens.append(("OP", matched_operator))
            index += len(matched_operator)
            continue
        if char.isalpha() or char == "_":
            start = index
            while index < length and (marker[index].isalnum() or marker[index] in "_."):
                index += 1
            word = marker[start:index]
            lowered = word.lower()
            if lowered in ("and", "or"):
                tokens.append(("BOOL", lowered))
            elif lowered == "in":
                tokens.append(("OP", "in"))
            elif lowered == "not":
                tokens.append(("NOT", "not"))
            else:
                tokens.append(("VAR", word))
            continue
        raise InvalidMarker(f"Unexpected character {char!r} in marker: {marker!r}")
    return tokens


class _Parser:
    def __init__(self, marker: str) -> None:
        self._tokens = _tokenize(marker)
        self._pos = 0
        self._marker = marker

    def _peek(self) -> Optional[Tuple[str, str]]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _next(self) -> Tuple[str, str]:
        token = self._peek()
        if token is None:
            raise InvalidMarker(f"Unexpected end of marker: {self._marker!r}")
        self._pos += 1
        return token

    def parse(self) -> _Node:
        node = self._parse_or()
        if self._peek() is not None:
            raise InvalidMarker(f"Trailing tokens in marker: {self._marker!r}")
        return node

    def _parse_or(self) -> _Node:
        nodes = [self._parse_and()]
        while self._peek() == ("BOOL", "or"):
            self._next()
            nodes.append(self._parse_and())
        return nodes[0] if len(nodes) == 1 else ("or", nodes)

    def _parse_and(self) -> _Node:
        nodes = [self._parse_atom()]
        while self._peek() == ("BOOL", "and"):
            self._next()
            nodes.append(self._parse_atom())
        return nodes[0] if len(nodes) == 1 else ("and", nodes)

    def _parse_atom(self) -> _Node:
        token = self._peek()
        if token is not None and token[0] == "LPAREN":
            self._next()
            node = self._parse_or()
            closing = self._next()
            if closing[0] != "RPAREN":
                raise InvalidMarker(f"Expected ')' in marker: {self._marker!r}")
            return node
        return self._parse_comparison()

    def _parse_comparison(self) -> _Node:
        lhs = self._parse_value()
        op = self._parse_operator()
        rhs = self._parse_value()
        return ("cmp", lhs, op, rhs)

    def _parse_operator(self) -> str:
        token = self._next()
        if token[0] == "NOT":
            following = self._next()
            if following != ("OP", "in"):
                raise InvalidMarker(f"Expected 'not in' in marker: {self._marker!r}")
            return "not in"
        if token[0] == "OP":
            return token[1]
        raise InvalidMarker(f"Expected operator in marker: {self._marker!r}")

    def _parse_value(self) -> _Value:
        token = self._next()
        if token[0] == "STR":
            return ("str", token[1])
        if token[0] == "VAR":
            if token[1] not in _VARIABLES:
                raise InvalidMarker(f"Unknown marker variable {token[1]!r}: {self._marker!r}")
            return ("var", token[1])
        raise InvalidMarker(f"Expected value in marker: {self._marker!r}")


def _normalize_node(node: _Node) -> _Node:
    """Canonicalize any ``extra`` literal in the parsed marker (PEP 685)."""
    kind = node[0]
    if kind in ("and", "or"):
        return (kind, [_normalize_node(child) for child in node[1]])
    _, lhs, op, rhs = node
    if lhs == ("var", "extra") and rhs[0] == "str":
        rhs = ("str", canonicalize_name(rhs[1]))
    elif rhs == ("var", "extra") and lhs[0] == "str":
        lhs = ("str", canonicalize_name(lhs[1]))
    return ("cmp", lhs, op, rhs)


def _eval_op(lhs: str, op: str, rhs: str, key: str) -> bool:
    if key in _MARKERS_REQUIRING_VERSION:
        try:
            spec = Specifier(f"{op}{rhs}")
        except InvalidSpecifier:
            pass
        else:
            return spec.contains(lhs, prereleases=True)
    oper = _STRING_OPERATORS.get(op)
    if oper is None:
        raise UndefinedComparison(f"Undefined {op!r} on {lhs!r} and {rhs!r}.")
    return oper(lhs, rhs)


def _evaluate(node: _Node, environment: Mapping[str, str]) -> bool:
    kind = node[0]
    if kind == "or":
        return any(_evaluate(child, environment) for child in node[1])
    if kind == "and":
        return all(_evaluate(child, environment) for child in node[1])

    _, lhs, op, rhs = node
    if lhs[0] == "var":
        key = lhs[1]
        try:
            lhs_value = environment[key]
        except KeyError as exc:
            raise UndefinedEnvironmentName(f"{key!r} does not exist in evaluation environment.") from exc
        rhs_value = rhs[1]
    else:
        key = rhs[1]
        try:
            rhs_value = environment[key]
        except KeyError as exc:
            raise UndefinedEnvironmentName(f"{key!r} does not exist in evaluation environment.") from exc
        lhs_value = lhs[1]
    return _eval_op(lhs_value, op, rhs_value, key)


class Marker:
    def __init__(self, marker: str) -> None:
        self._markers: _Node = _normalize_node(_Parser(marker).parse())

    def __str__(self) -> str:
        return _format_node(self._markers, top_level=True)

    def __repr__(self) -> str:
        return f"<Marker('{self}')>"

    def evaluate(self, environment: Optional[Mapping[str, str]] = None) -> bool:
        current: Dict[str, str] = default_environment()
        current["extra"] = ""
        if environment is not None:
            current.update(environment)
            if "extra" in current:
                extra = current["extra"]
                current["extra"] = canonicalize_name(extra) if extra else ""
        return _evaluate(self._markers, current)


def _format_value(value: _Value) -> str:
    if value[0] == "var":
        return value[1]
    return f'"{value[1]}"'


def _format_node(node: _Node, top_level: bool = False) -> str:
    kind = node[0]
    if kind in ("and", "or"):
        inner = f" {kind} ".join(_format_node(child) for child in node[1])
        return inner if top_level else f"({inner})"
    _, lhs, op, rhs = node
    return f"{_format_value(lhs)} {op} {_format_value(rhs)}"
