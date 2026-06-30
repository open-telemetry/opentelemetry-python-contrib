# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase

from opentelemetry.instrumentation.pika.utils import _PikaGetter


class TestPikaGetter(TestCase):
    def setUp(self) -> None:
        self.getter = _PikaGetter()

    def test_get_none(self) -> None:
        carrier = {}
        value = self.getter.get(carrier, "test")
        self.assertIsNone(value)

    def test_get_value(self) -> None:
        key = "test"
        value = "value"
        carrier = {key: value}
        val = self.getter.get(carrier, key)
        self.assertEqual(val, [value])

    def test_keys(self):
        keys = self.getter.keys({})
        self.assertEqual(keys, [])
