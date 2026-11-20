# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest

from opentelemetry.instrumentation.confluent_kafka.utils import (
    KafkaPropertiesExtractor,
)


class TestKafkaPropertiesExtractor(unittest.TestCase):
    def test_extract_produce_partition(self):
        # Test with args
        args = ("topic", "value", "key", 1)
        kwargs = {}
        self.assertEqual(KafkaPropertiesExtractor.extract_produce_partition(args, kwargs), 1)

        # Test with kwargs
        args = ()
        kwargs = {"partition": 2}
        self.assertEqual(KafkaPropertiesExtractor.extract_produce_partition(args, kwargs), 2)

        # Test with no partition
        args = ()
        kwargs = {}
        self.assertIsNone(KafkaPropertiesExtractor.extract_produce_partition(args, kwargs))
