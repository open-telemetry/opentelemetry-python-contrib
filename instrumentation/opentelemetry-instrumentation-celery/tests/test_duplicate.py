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
