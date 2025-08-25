# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
