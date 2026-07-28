# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase, main

from opentelemetry.instrumentation._packaging.version import (
    InvalidVersion,
    Version,
    parse,
)


class TestVersion(TestCase):
    def test_parse_returns_version(self):
        """PEP 440 -- a normal public version identifier (a plain release
        segment such as "1.2.3") parses to a Version."""
        self.assertIsInstance(parse("1.2.3"), Version)

    def test_release_tuple(self):
        """PEP 440, Release segment: "Comparison and ordering of release
        segments considers the numeric value of each component of the release
        segment in turn." ``.release`` exposes those components as ints."""
        self.assertEqual(parse("1.4").release, (1, 4))
        self.assertEqual(parse("2.0.0").release, (2, 0, 0))
        self.assertEqual(parse("v1.2.3").release, (1, 2, 3))

    def test_release_tuple_comparison(self):
        """PEP 440, Release segment: "Comparison and ordering of release
        segments considers the numeric value of each component of the release
        segment in turn." (This is the comparison the sqlalchemy
        instrumentation performs on ``.release``.)"""
        self.assertTrue(parse("1.4.0").release >= (1, 4))
        self.assertTrue(parse("2.0.0").release >= (1, 4))
        self.assertFalse(parse("1.3.5").release >= (1, 4))

    def test_ordering(self):
        """PEP 440, Version ordering: "X.Y and X.Y.0 are not considered
        distinct release numbers, as the release segment comparison rules
        implicit expand the two component form to X.Y.0 when comparing it to
        any release segment that includes three components.\" """
        self.assertLess(parse("2.1.9"), parse("2.2.0"))
        self.assertGreaterEqual(parse("3.0.0"), parse("3.0.0"))
        self.assertGreater(parse("4.0"), parse("3.1.0"))
        self.assertEqual(parse("1.0"), parse("1.0.0"))

    def test_prerelease_ordering(self):
        """PEP 440, Summary of permitted suffixes and relative ordering:
        "Within a numeric release (1.0, 2.7.3), the following suffixes are
        permitted and MUST be ordered as shown: .devN, aN, bN, rcN,
        <no suffix>, .postN\" """
        self.assertLess(parse("1.0a1"), parse("1.0a2"))
        self.assertLess(parse("1.0a2"), parse("1.0b1"))
        self.assertLess(parse("1.0b1"), parse("1.0rc1"))
        self.assertLess(parse("1.0rc1"), parse("1.0"))
        self.assertLess(parse("1.0.dev1"), parse("1.0a1"))
        self.assertLess(parse("1.0"), parse("1.0.post1"))

    def test_prerelease_letter_normalization(self):
        """PEP 440, Pre-release spelling: "Pre-releases allow the additional
        spellings of alpha, beta, c, pre, and preview for a, b, rc, rc, and rc
        respectively." Also: "Installation tools SHOULD interpret c versions
        as being equivalent to rc versions (that is, c1 indicates the same
        version as rc1).\" """
        self.assertEqual(parse("1.0alpha1"), parse("1.0a1"))
        self.assertEqual(parse("1.0beta1"), parse("1.0b1"))
        self.assertEqual(parse("1.0c1"), parse("1.0rc1"))
        self.assertEqual(parse("1.0preview1"), parse("1.0rc1"))

    def test_predicates(self):
        """PEP 440, developmental and post-release segments: "The
        developmental release segment consists of the string .dev, followed by
        a non-negative integer value." / "The post-release segment consists of
        the string .post, followed by a non-negative integer value.\" """
        self.assertTrue(parse("1.0rc1").is_prerelease)
        self.assertTrue(parse("1.0.dev1").is_prerelease)
        self.assertTrue(parse("1.0.dev1").is_devrelease)
        self.assertTrue(parse("1.0.post1").is_postrelease)
        self.assertFalse(parse("1.0").is_prerelease)
        self.assertFalse(parse("1.0").is_postrelease)

    def test_epoch_and_local(self):
        """PEP 440, Version epochs: "If included in a version identifier, the
        epoch appears before all other components, separated from the release
        segment by an exclamation mark: E!X.Y." Local version identifiers: "If
        a segment consists entirely of ASCII digits then that section should be
        considered an integer for comparison purposes ...\" """
        self.assertGreater(parse("1!1.0"), parse("2.0"))
        self.assertEqual(parse("1!1.0").epoch, 1)
        self.assertEqual(parse("1.0+abc").local, "abc")
        self.assertGreater(parse("1.0+abc.2"), parse("1.0+abc.1"))

    def test_str_normalization(self):
        """PEP 440, Normalization -- the canonical string form uses the
        normalized pre-release spelling: "Pre-releases allow the additional
        spellings of alpha, beta, c, pre, and preview for a, b, rc, rc, and rc
        respectively." (so "1.0alpha1" normalizes to "1.0a1")."""
        self.assertEqual(str(parse("1.0")), "1.0")
        self.assertEqual(str(parse("v1.0.0")), "1.0.0")
        self.assertEqual(str(parse("1.0alpha1")), "1.0a1")

    def test_hash_equal_versions(self):
        """PEP 440, Version ordering: "X.Y and X.Y.0 are not considered
        distinct release numbers ...", so equal versions must hash equally."""
        self.assertEqual(hash(parse("1.0")), hash(parse("1.0.0")))

    def test_invalid_version(self):
        """PEP 440 -- strings that are not valid version identifiers are
        rejected with InvalidVersion."""
        for value in ("", "abc", "1..0", "not-a-version", "1.0.0+"):
            with self.assertRaises(InvalidVersion):
                Version(value)

    def test_invalid_version_is_value_error(self):
        """InvalidVersion subclasses ValueError, matching packaging so callers
        can keep catching ValueError."""
        self.assertIsInstance(InvalidVersion(), ValueError)


if __name__ == "__main__":
    main()
