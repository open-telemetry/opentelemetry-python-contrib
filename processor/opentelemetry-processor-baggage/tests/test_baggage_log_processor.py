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

import re
import unittest

from opentelemetry.baggage import set_baggage
from opentelemetry.context import attach, detach
from opentelemetry.processor.baggage import (
    ALLOW_ALL_BAGGAGE_KEYS,
    BaggageLogProcessor,
)
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    BatchLogRecordProcessor,
)


class BaggageLogProcessorTest(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemoryLogRecordExporter()
        self.logger_provider = LoggerProvider()
        self.logger_provider.add_log_record_processor(
            BaggageLogProcessor(ALLOW_ALL_BAGGAGE_KEYS)
        )
        self.logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(self.exporter)
        )
        self.logger = self.logger_provider.get_logger("test-logger")

    def _get_attributes(self):
        self.logger_provider.force_flush()
        logs = self.exporter.get_finished_logs()
        self.assertTrue(len(logs) > 0)
        return logs[-1].log_record.attributes

    def test_check_the_baggage(self):
        self.assertIsInstance(
            BaggageLogProcessor(ALLOW_ALL_BAGGAGE_KEYS), LogRecordProcessor
        )

    def test_baggage_added_to_log_record(self):
        token = attach(set_baggage("queen", "bee"))
        self.logger.emit(None)
        attributes = self._get_attributes()
        self.assertEqual(attributes.get("queen"), "bee")
        detach(token)

    def test_baggage_with_prefix(self):
        token = attach(set_baggage("queen", "bee"))
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(
            BaggageLogProcessor(lambda key: key.startswith("que"))
        )
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter)
        )
        logger = logger_provider.get_logger("test-logger")
        logger.emit(None)
        logger_provider.force_flush()
        logs = exporter.get_finished_logs()
        attributes = logs[-1].log_record.attributes
        self.assertEqual(attributes.get("queen"), "bee")
        detach(token)

    def test_baggage_with_regex(self):
        token = attach(set_baggage("queen", "bee"))
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(
            BaggageLogProcessor(
                lambda key: re.match(r"que.*", key) is not None
            )
        )
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter)
        )
        logger = logger_provider.get_logger("test-logger")
        logger.emit(None)
        logger_provider.force_flush()
        logs = exporter.get_finished_logs()
        attributes = logs[-1].log_record.attributes
        self.assertEqual(attributes.get("queen"), "bee")
        detach(token)

    def test_no_baggage_not_added(self):
        self.logger.emit(None)
        self.logger_provider.force_flush()
        logs = self.exporter.get_finished_logs()
        self.assertTrue(len(logs) > 0)
        attributes = logs[-1].log_record.attributes
        self.assertNotIn("queen", attributes)

    @staticmethod
    def has_prefix(baggage_key: str) -> bool:
        return baggage_key.startswith("que")

    @staticmethod
    def matches_regex(baggage_key: str) -> bool:
        return re.match(r"que.*", baggage_key) is not None
    def test_multiple_predicates(self):
        token1 = attach(set_baggage("queen", "bee"))
        token2 = attach(set_baggage("king", "cobra"))
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(
            BaggageLogProcessor([
                lambda key: key.startswith("que"),
                lambda key: key.startswith("kin"),
            ])
        )
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter)
        )
        logger = logger_provider.get_logger("test-logger")
        logger.emit(None)
        logger_provider.force_flush()
        logs = exporter.get_finished_logs()
        attributes = logs[-1].log_record.attributes
        self.assertEqual(attributes.get("queen"), "bee")
        self.assertEqual(attributes.get("king"), "cobra")
        detach(token2)
        detach(token1)


if __name__ == "__main__":
    unittest.main()
    