# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry.instrumentation.http_base.version import __version__


class TestHttpBase(TestCase):
    def test_version(self) -> None:
        self.assertIsInstance(__version__, str)
        self.assertTrue(__version__)
