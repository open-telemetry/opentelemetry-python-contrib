# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import re
from contextlib import AbstractContextManager
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from tests._util import assert_logs

from opentelemetry.instrumentation.http._internal._env import (
    parse_bool_env_var,
    parse_int_env_var,
    parse_list_env_var,
    parse_patterns_env_var,
)

_VAR = "OTEL_TEST_VAR"


def _env(value: str | None) -> AbstractContextManager[Any]:
    """Sets ``_VAR`` to ``value`` in an otherwise empty environment, or leaves it unset for ``None``."""
    return patch.dict(os.environ, {} if value is None else {_VAR: value}, clear=True)


class TestParseBoolEnvVar(TestCase):
    _CASES: tuple[tuple[str | None, bool | None, bool], ...] = (
        ("true", True, False),
        (" TRUE ", True, False),
        ("tRuE", True, False),
        ("false", False, False),
        ("False", False, False),
        ("\tfalse\n", False, False),
        (None, None, False),
        ("", None, False),
        ("  ", None, False),
        ("yes", None, True),
        ("1", None, True),
        ("0", None, True),
        ("on", None, True),
        ("true false", None, True),
    )

    def test_parse(self) -> None:
        for value, expected, warns in self._CASES:
            with self.subTest(value=value), _env(value), assert_logs(self, contains=_VAR, present=warns):
                self.assertIs(parse_bool_env_var(_VAR), expected)


class TestParseIntEnvVar(TestCase):
    _CASES: tuple[tuple[str | None, int | None, bool], ...] = (
        ("1024", 1024, False),
        (" 0 ", 0, False),
        ("-1", -1, False),
        ("+5", 5, False),
        ("007", 7, False),
        (None, None, False),
        ("", None, False),
        ("  ", None, False),
        ("abc", None, True),
        ("1.5", None, True),
        ("1e3", None, True),
        ("0x10", None, True),
    )

    def test_parse(self) -> None:
        for value, expected, warns in self._CASES:
            with self.subTest(value=value), _env(value), assert_logs(self, contains=_VAR, present=warns):
                self.assertEqual(parse_int_env_var(_VAR), expected)


class TestParseListEnvVar(TestCase):
    _CASES: tuple[tuple[str | None, tuple[str, ...] | None], ...] = (
        (" GET , POST,, ", ("GET", "POST")),
        ("GET", ("GET",)),
        ("a,b,c", ("a", "b", "c")),
        ("a b, c", ("a b", "c")),
        (None, None),
        ("", None),
        (" ", None),
        (" , ", None),
        (",,,", None),
    )

    def test_parse(self) -> None:
        for value, expected in self._CASES:
            with self.subTest(value=value), _env(value):
                self.assertEqual(parse_list_env_var(_VAR), expected)


class TestParsePatternsEnvVar(TestCase):
    _CASES: tuple[tuple[str | None, list[str] | None, bool], ...] = (
        ("content-type, x-.*", ["content-type", "x-.*"], False),
        ("^x-[a-z]+$", ["^x-[a-z]+$"], False),
        ("a|b, c", ["a|b", "c"], False),
        (None, None, False),
        ("", None, False),
        (" , ", None, False),
        # A single invalid entry unsets the whole variable.
        ("content-type,[bad", None, True),
        ("(unclosed", None, True),
        ("*", None, True),
    )

    def test_parse(self) -> None:
        for value, expected, warns in self._CASES:
            with self.subTest(value=value):
                with _env(value), assert_logs(self, contains=_VAR, present=warns):
                    patterns = parse_patterns_env_var(_VAR, re.IGNORECASE)

                if expected is None:
                    self.assertIsNone(patterns)
                    continue
                assert patterns is not None
                self.assertEqual([pattern.pattern for pattern in patterns], expected)
                self.assertTrue(all(pattern.flags & re.IGNORECASE for pattern in patterns))
