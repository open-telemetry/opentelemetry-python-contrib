# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry._logs import SeverityNumber
from opentelemetry.instrumentation.log_utils import std_to_otel


class TestLogUtils(TestCase):
    def test_std_to_otel(self):
        for levelno, expected in (
            (0, SeverityNumber.UNSPECIFIED),
            (9, SeverityNumber.UNSPECIFIED),
            (10, SeverityNumber.DEBUG),
            (14, SeverityNumber.DEBUG4),
            (20, SeverityNumber.INFO),
            (30, SeverityNumber.WARN),
            (40, SeverityNumber.ERROR),
            (50, SeverityNumber.FATAL),
            (53, SeverityNumber.FATAL4),
            (54, SeverityNumber.FATAL4),
        ):
            with self.subTest(levelno=levelno):
                self.assertEqual(std_to_otel(levelno), expected)
