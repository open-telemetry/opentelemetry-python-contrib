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

from opentelemetry.instrumentation.confluent_kafka.utils import (
    KafkaPropertiesExtractor,
)


class TestKafkaPropertiesExtractor(unittest.TestCase):
    def test_extract_produce_partition(self):
        # Test with args
        args = ("topic", "value", "key", 1)
        kwargs = {}
        self.assertEqual(
            KafkaPropertiesExtractor.extract_produce_partition(args, kwargs), 1
        )

        # Test with kwargs
        args = ()
        kwargs = {"partition": 2}
        self.assertEqual(
            KafkaPropertiesExtractor.extract_produce_partition(args, kwargs), 2
        )

        # Test with no partition
        args = ()
        kwargs = {}
        self.assertIsNone(
            KafkaPropertiesExtractor.extract_produce_partition(args, kwargs)
        )
