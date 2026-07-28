# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase, main

from opentelemetry.instrumentation._packaging.specifiers import (
    InvalidSpecifier,
    Specifier,
    SpecifierSet,
)


class TestSpecifierSet(TestCase):
    def test_simple_bounds(self):
        """PEP 440, Inclusive/exclusive ordered comparison: "Comparison and
        ordering of release segments considers the numeric value of each
        component of the release segment in turn." (">=2.2.0,<4.0" combines an
        inclusive lower bound with an exclusive upper bound.)"""
        spec = SpecifierSet(">=2.2.0,<4.0")
        self.assertTrue(spec.contains("2.2.0"))
        self.assertTrue(spec.contains("3.5.1"))
        self.assertFalse(spec.contains("2.1.9"))
        self.assertFalse(spec.contains("4.0"))
        self.assertFalse(spec.contains("4.0.0"))

    def test_compatible_release(self):
        """PEP 440, Compatible release: "For a given release identifier V.N,
        the compatible release clause is approximately equivalent to the pair
        of comparison clauses: >= V.N, == V.*\" """
        spec = SpecifierSet("~=1.4")
        self.assertTrue(spec.contains("1.4.5"))
        self.assertFalse(spec.contains("2.0"))

    def test_wildcard_equal(self):
        """PEP 440, Version matching: "Prefix matching may be requested instead
        of strict comparison, by appending a trailing .* to the version
        identifier in the version matching clause. This means that additional
        trailing segments will be ignored ...\" """
        spec = SpecifierSet("==1.4.*")
        self.assertTrue(spec.contains("1.4.9"))
        self.assertFalse(spec.contains("1.5"))

    def test_not_equal(self):
        """PEP 440, Version exclusion: "The allowed version identifiers and
        comparison semantics are the same as those of the Version matching
        operator, except that the sense of any match is inverted.\" """
        spec = SpecifierSet("!=1.5")
        self.assertFalse(spec.contains("1.5"))
        self.assertTrue(spec.contains("1.6"))

    def test_empty_set_matches_any_final(self):
        """PEP 440 -- an empty specifier imposes no version constraint, but
        default pre-release handling still applies: "Pre-releases ... are
        implicitly excluded from all version specifiers, unless ...\" """
        spec = SpecifierSet("")
        self.assertTrue(spec.contains("1.0"))
        self.assertTrue(spec.contains("99.9"))

    def test_prerelease_default_excluded(self):
        """PEP 440, Handling of pre-releases: "Pre-releases of any kind,
        including developmental releases, are implicitly excluded from all
        version specifiers, unless they are already present on the system,
        explicitly requested by the user, or if the only available version
        that satisfies the version specifier is a pre-release." So a
        pre-release of the lower bound is excluded, while an in-range
        pre-release with no final alternative is admitted."""
        spec = SpecifierSet(">=1.0")
        self.assertFalse(spec.contains("1.0.0rc1"))
        self.assertTrue(spec.contains("2.0.0rc1"))

    def test_prerelease_explicit(self):
        """PEP 440, Handling of pre-releases -- an in-range pre-release is
        admitted by default (no final alternative present) but excluded when
        pre-releases are explicitly disallowed: "Pre-releases ... are
        implicitly excluded from all version specifiers, unless ...\" """
        spec = SpecifierSet(">=1.0")
        self.assertTrue(spec.contains("2.0.0rc1"))
        self.assertFalse(spec.contains("2.0.0rc1", prereleases=False))

    def test_specifier_in_a_prerelease_spec(self):
        """PEP 440, Handling of pre-releases -- a specifier that itself names a
        pre-release accepts pre-releases: "... unless they are already present
        on the system, explicitly requested by the user ...\" """
        spec = SpecifierSet(">=2.0b0")
        self.assertTrue(spec.contains("2.0b0"))

    def test_filter_prefers_final_releases(self):
        """PEP 440, Handling of pre-releases -- filtering drops pre-releases
        when final releases are available, but yields them when they are "the
        only available version that satisfies the version specifier.\" """
        spec = SpecifierSet(">=1.0")
        self.assertEqual(
            list(spec.filter(["1.0", "2.0a1", "2.0"])), ["1.0", "2.0"]
        )
        self.assertEqual(list(spec.filter(["2.0a1"])), ["2.0a1"])

    def test_str_is_sorted(self):
        """The string form of a SpecifierSet is deterministic (clauses in a
        stable order), matching packaging's canonical rendering."""
        self.assertEqual(str(SpecifierSet("<4.0,>=2.2.0")), "<4.0,>=2.2.0")

    def test_invalid_specifier(self):
        """PEP 440 -- malformed clauses are rejected. Note ~=1 is invalid:
        "This operator MUST NOT be used with a single segment version number
        such as ~=1.\" """
        for value in ("=>1.0", "1.0", "~=1", "==1.*.5"):
            with self.assertRaises(InvalidSpecifier):
                Specifier(value)


if __name__ == "__main__":
    main()
