# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest

from opentelemetry.util.genai.version import __version__


class TestVersion(unittest.TestCase):
    def test_version_exists(self):
        """Test that version is defined and is a string."""
        self.assertIsInstance(__version__, str)
        self.assertTrue(len(__version__) > 0)

    def test_version_format(self):
        """Test that version follows expected format."""
        # Should be in format like "0.1b0.dev" or similar
        self.assertRegex(__version__, r"^\d+\.\d+.*")
