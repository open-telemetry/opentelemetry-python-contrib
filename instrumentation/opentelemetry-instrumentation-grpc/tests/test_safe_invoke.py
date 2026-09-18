# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from functools import partial
from unittest import TestCase

from opentelemetry.instrumentation.grpc._client import _safe_invoke


class _CallableWithoutName:
    def __init__(self):
        self.calls = 0

    def __call__(self, value):
        self.calls += 1
        self.value = value


class _RaisingCallable:
    def __init__(self):
        self.calls = 0

    def __call__(self, _value):
        self.calls += 1
        raise RuntimeError("hook failed")


class _CallableWithBrokenName:
    def __init__(self):
        self.calls = 0

    def __getattribute__(self, name):
        if name == "__name__":
            raise RuntimeError("name lookup failed")
        return object.__getattribute__(self, name)

    def __call__(self, _value):
        self.calls += 1


class TestSafeInvoke(TestCase):
    def test_named_function_is_invoked(self):
        calls = []

        def hook(value):
            calls.append(value)

        _safe_invoke(hook, "value")

        self.assertEqual(calls, ["value"])

    def test_callable_without_name_is_invoked(self):
        hook = _CallableWithoutName()

        _safe_invoke(hook, "value")

        self.assertEqual(hook.calls, 1)
        self.assertEqual(hook.value, "value")

    def test_partial_is_invoked(self):
        calls = []

        def hook(values, value):
            values.append(value)

        _safe_invoke(partial(hook, calls), "value")

        self.assertEqual(calls, ["value"])

    def test_raising_callable_is_invoked_and_logged(self):
        hook = _RaisingCallable()

        with self.assertLogs("opentelemetry.instrumentation.grpc._client", level=logging.ERROR) as logs:
            _safe_invoke(hook, "value")

        self.assertEqual(hook.calls, 1)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("<unknown>", logs.output[0])
        self.assertIn("hook failed", logs.output[0])

    def test_broken_name_lookup_uses_fallback(self):
        hook = _CallableWithBrokenName()

        with self.assertLogs("opentelemetry.instrumentation.grpc._client", level=logging.ERROR) as logs:
            _safe_invoke(hook, "value")

        self.assertEqual(hook.calls, 0)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("<unknown>", logs.output[0])
        self.assertNotIn("UnboundLocalError", logs.output[0])
