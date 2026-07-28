# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase, main

from opentelemetry.instrumentation._packaging.requirements import (
    InvalidRequirement,
    Requirement,
)


class TestRequirement(TestCase):
    def test_name_and_specifier(self):
        """PEP 508 grammar: "name = identifier" followed by an optional
        "versionspec"; the version comparison operators are
        "version_cmp = wsp* '<' | '<=' | '!=' | '==' | '>=' | '>' | '~=' |
        '==='" and "Versions may be specified according to the PEP 440
        rules.\" """
        req = Requirement("flask >= 2.2.0, < 4.0")
        self.assertEqual(req.name, "flask")
        self.assertEqual(str(req.specifier), "<4.0,>=2.2.0")
        self.assertIsNone(req.marker)
        self.assertTrue(req.specifier.contains("3.0.0"))

    def test_name_with_separators(self):
        """PEP 508 name grammar (matched case-insensitively):
        "^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$" -- so '-' and '_' are
        legal interior separators in a distribution name."""
        self.assertEqual(
            Requirement("google-cloud-aiplatform >= 1.64").name,
            "google-cloud-aiplatform",
        )
        self.assertEqual(Requirement("aio_pika >= 7.2.0").name, "aio_pika")

    def test_no_specifier(self):
        """PEP 508 -- the "versionspec" is optional, so a bare name is a valid
        requirement that constrains no version."""
        req = Requirement("pytest")
        self.assertEqual(req.name, "pytest")
        self.assertEqual(len(req.specifier), 0)
        self.assertTrue(req.specifier.contains("1.2.3"))

    def test_extras(self):
        """PEP 508 extras grammar: "extras = '[' wsp* extras_list? wsp* ']'"
        with "extras_list = identifier (wsp* ',' wsp* identifier)*.\" """
        req = Requirement("requests[security,socks] >= 2.0")
        self.assertEqual(req.name, "requests")
        self.assertEqual(req.extras, {"security", "socks"})

    def test_marker(self):
        """PEP 508 -- a requirement may carry an environment marker after ';'.
        This is exactly how the instrumentation declares its instrumented
        library via the 'extra' marker (extra == "instruments")."""
        req = Requirement('flask >= 2.2.0; extra == "instruments"')
        self.assertEqual(req.name, "flask")
        self.assertIsNotNone(req.marker)
        self.assertTrue(req.marker.evaluate({"extra": "instruments"}))
        self.assertFalse(req.marker.evaluate({"extra": "other"}))

    def test_str_roundtrip(self):
        """PEP 508 -- a parsed requirement renders back to its canonical
        string form (name + specifier + "; " + marker)."""
        self.assertEqual(
            str(Requirement('test-pkg ~= 1.0; extra == "instruments"')),
            'test-pkg~=1.0; extra == "instruments"',
        )

    def test_invalid_requirement(self):
        """PEP 508 -- strings that do not conform to the requirement grammar
        are rejected with InvalidRequirement."""
        for value in ("", "== 1.0", "flask >= not-a-version"):
            with self.assertRaises(InvalidRequirement):
                Requirement(value)


if __name__ == "__main__":
    main()
