# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry.instrumentation.http.version import __version__


class TestVersion(TestCase):
    def test_version_is_non_empty_string(self) -> None:
        self.assertIsInstance(__version__, str)
        self.assertTrue(__version__)
