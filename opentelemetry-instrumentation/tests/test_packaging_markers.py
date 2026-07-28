# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase, main

from opentelemetry.instrumentation._packaging.markers import (
    InvalidMarker,
    Marker,
)


class TestMarker(TestCase):
    def test_extra_equality(self):
        """PEP 508, the 'extra' marker variable: "The 'extra' variable is
        special. It is used by wheels to signal which specifications apply to a
        given extra in the wheel METADATA file ..." This is the only marker the
        instrumentation actually evaluates."""
        marker = Marker('extra == "instruments"')
        self.assertTrue(marker.evaluate({"extra": "instruments"}))
        self.assertFalse(marker.evaluate({"extra": "other"}))
        self.assertFalse(marker.evaluate({"extra": ""}))

    def test_extra_name_is_normalized(self):
        """PEP 685, extra name normalization: "When comparing extra names,
        tools MUST normalize the names being compared using the semantics
        outlined in PEP 503 for names: re.sub(r'[-_.]+', '-', name).lower()".
        So "Instruments-Any", "instruments-any" and "Instruments_Any" all
        compare equal."""
        marker = Marker('extra == "Instruments-Any"')
        self.assertTrue(marker.evaluate({"extra": "instruments-any"}))
        self.assertTrue(marker.evaluate({"extra": "Instruments_Any"}))

    def test_python_version(self):
        """PEP 508 -- python_version is a version field, so per the Dependency
        Specifiers spec its comparisons "use the PEP 440 version comparison
        rules when those are defined (that is when both sides have a valid
        version specifier)"."""
        self.assertTrue(
            Marker('python_version >= "3.0"').evaluate(
                {"python_version": "3.12"}
            )
        )
        self.assertFalse(
            Marker('python_version >= "3.20"').evaluate(
                {"python_version": "3.12"}
            )
        )

    def test_and_or(self):
        """PEP 508 marker grammar -- markers combine with boolean operators
        (capture/action annotations elided):
            marker_and = marker_expr 'and' marker_expr | marker_expr
            marker_or  = marker_and 'or' marker_and | marker_and"""
        marker = Marker('python_version >= "3.0" and extra == "instruments"')
        self.assertTrue(
            marker.evaluate({"python_version": "3.12", "extra": "instruments"})
        )
        self.assertFalse(
            marker.evaluate({"python_version": "3.12", "extra": "other"})
        )

        marker = Marker('extra == "a" or extra == "b"')
        self.assertTrue(marker.evaluate({"extra": "b"}))

    def test_parentheses(self):
        """PEP 508 marker grammar -- a parenthesized marker is itself a
        marker_expr (capture/action annotations elided):
            marker_expr = marker_var marker_op marker_var | '(' marker ')'
        so an 'or' can be nested inside an 'and'."""
        marker = Marker(
            '(extra == "a" or extra == "b") and python_version >= "3.0"'
        )
        self.assertTrue(
            marker.evaluate({"extra": "a", "python_version": "3.12"})
        )
        self.assertFalse(
            marker.evaluate({"extra": "c", "python_version": "3.12"})
        )

    def test_string_ordering_operators(self):
        """PyPA Dependency Specifiers spec (supersedes PEP 508) on ordered
        comparisons of string fields: "... locking and installation tools
        SHOULD implement the following behavior: treat >= and <= as equivalent
        to == and treat > and < as always being False." sys_platform is a
        string field, so "<"/">" are always False and "<="/">=" reduce to
        equality. (PEP 508's older wording instead fell back to Python string
        comparison here.)"""
        env = {"sys_platform": "linux"}
        self.assertFalse(Marker('sys_platform < "z"').evaluate(env))
        self.assertFalse(Marker('sys_platform < "a"').evaluate(env))
        self.assertFalse(Marker('sys_platform > "a"').evaluate(env))
        self.assertFalse(Marker('sys_platform > "z"').evaluate(env))
        self.assertTrue(Marker('sys_platform <= "linux"').evaluate(env))
        self.assertFalse(Marker('sys_platform <= "z"').evaluate(env))
        self.assertTrue(Marker('sys_platform >= "linux"').evaluate(env))
        self.assertFalse(Marker('sys_platform >= "a"').evaluate(env))

    def test_invalid_marker(self):
        """PEP 508 -- a malformed marker, or one referencing a variable not in
        the defined env_var set, is rejected with InvalidMarker."""
        for value in ('extra = "x"', "extra ==", 'unknown_var == "x"'):
            with self.assertRaises(InvalidMarker):
                Marker(value)


if __name__ == "__main__":
    main()
