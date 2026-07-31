# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest

from opentelemetry.instrumentation.celery import CeleryInstrumentor


class TestUtils(unittest.TestCase):
    def test_duplicate_instrumentaion(self):
        first = CeleryInstrumentor()
        first.instrument()
        second = CeleryInstrumentor()
        second.instrument()
        CeleryInstrumentor().uninstrument()
        self.assertIsNotNone(first.metrics)
        self.assertIsNotNone(second.metrics)
        self.assertEqual(first.task_id_to_start_time, {})
        self.assertEqual(second.task_id_to_start_time, {})
