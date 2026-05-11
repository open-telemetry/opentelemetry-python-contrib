# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

from opentelemetry.instrumentation.wsgi import WSGIGetter


class TestGetter(TestCase):
    def test_get_none(self):
        getter = WSGIGetter()
        carrier = {}
        val = getter.get(carrier, "test")

        self.assertIsNone(val)

    def test_get(self):
        getter = WSGIGetter()
        carrier = {"HTTP_TEST_KEY": "val"}
        val = getter.get(carrier, "test-key")

        self.assertEqual(val, ["val"])

    def test_keys(self):
        getter = WSGIGetter()
        keys = getter.keys(
            {
                "HTTP_TEST_KEY": "val",
                "HTTP_OTHER_KEY": 42,
                "NON_HTTP_KEY": "val",
            }
        )

        self.assertEqual(keys, ["test-key", "other-key"])

    def test_keys_empty(self):
        getter = WSGIGetter()
        keys = getter.keys({})

        self.assertEqual(keys, [])
