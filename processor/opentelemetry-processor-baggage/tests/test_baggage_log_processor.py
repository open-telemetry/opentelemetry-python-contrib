# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import re
import unittest
from importlib.metadata import entry_points

from opentelemetry.baggage import set_baggage
from opentelemetry.context import attach, detach
from opentelemetry.processor.baggage import (
    ALLOW_ALL_BAGGAGE_KEYS,
    BaggageLogProcessor,
)
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    InMemoryLogRecordExporter,
)

# (included, excluded, baggage keys, expected copied keys)
_INCLUDE_EXCLUDE_CASES = (
    (None, None, ["a", "b"], ["a", "b"]),
    ([], [], ["a", "b"], ["a", "b"]),
    (["a*"], None, ["a", "ab", "b"], ["a", "ab"]),
    (None, ["a*"], ["a", "ab", "b"], ["b"]),
    (["a*", "b*"], ["ab*"], ["a", "ab", "abc", "b", "c"], ["a", "b"]),
    (["a", "b"], ["a"], ["a", "b", "c"], ["b"]),
    (["a?c"], None, ["abc", "ac", "abbc"], ["abc"]),
    (["foo"], None, ["foo", "foobar", "xfoo", "FOO"], ["foo"]),
    (["a.b", "[c]", "d+"], None, ["a.b", "axb", "[c]", "c", "d+", "dd"], ["a.b", "[c]", "d+"]),
)


def _baggage_context(keys):
    ctx = None
    for key in keys:
        ctx = set_baggage(key, "value", context=ctx)
    return ctx


class BaggageLogProcessorTest(unittest.TestCase):
    def setUp(self):
        self.exporter = InMemoryLogRecordExporter()
        self.logger_provider = LoggerProvider()
        self.logger_provider.add_log_record_processor(BaggageLogProcessor(ALLOW_ALL_BAGGAGE_KEYS))
        self.logger_provider.add_log_record_processor(BatchLogRecordProcessor(self.exporter))
        self.logger = self.logger_provider.get_logger("test-logger")

    def _get_attributes(self):
        self.logger_provider.force_flush()
        logs = self.exporter.get_finished_logs()
        self.assertTrue(len(logs) > 0)
        return logs[-1].log_record.attributes

    def test_check_the_baggage(self):
        self.assertIsInstance(BaggageLogProcessor(ALLOW_ALL_BAGGAGE_KEYS), LogRecordProcessor)

    def test_baggage_added_to_log_record(self):
        token = attach(set_baggage("queen", "bee"))
        self.logger.emit(None)
        attributes = self._get_attributes()
        self.assertEqual(attributes.get("queen"), "bee")
        detach(token)

    def test_baggage_with_prefix(self):
        token = attach(set_baggage("queen", "bee"))
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(BaggageLogProcessor(lambda key: key.startswith("que")))
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
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
        logger_provider.add_log_record_processor(BaggageLogProcessor(lambda key: re.match(r"que.*", key) is not None))
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
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

    def test_multiple_predicates(self):
        token1 = attach(set_baggage("queen", "bee"))
        token2 = attach(set_baggage("king", "cobra"))
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(
            BaggageLogProcessor(
                [
                    lambda key: key.startswith("que"),
                    lambda key: key.startswith("kin"),
                ]
            )
        )
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        logger = logger_provider.get_logger("test-logger")
        logger.emit(None)
        logger_provider.force_flush()
        logs = exporter.get_finished_logs()
        attributes = logs[-1].log_record.attributes
        self.assertEqual(attributes.get("queen"), "bee")
        self.assertEqual(attributes.get("king"), "cobra")
        detach(token2)
        detach(token1)

    def test_max_baggage_attributes_limit(self):
        token1 = attach(set_baggage("key1", "val1"))
        token2 = attach(set_baggage("key2", "val2"))
        token3 = attach(set_baggage("key3", "val3"))
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(BaggageLogProcessor(ALLOW_ALL_BAGGAGE_KEYS, max_baggage_attributes=2))
        exporter = InMemoryLogRecordExporter()
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        logger = logger_provider.get_logger("test-logger")
        logger.emit(None)
        logger_provider.force_flush()
        logs = exporter.get_finished_logs()
        attributes = logs[-1].log_record.attributes
        self.assertEqual(len(attributes), 2)
        detach(token3)
        detach(token2)
        detach(token1)

    @staticmethod
    def has_prefix(baggage_key: str) -> bool:
        return baggage_key.startswith("que")

    @staticmethod
    def matches_regex(baggage_key: str) -> bool:
        return re.match(r"que.*", baggage_key) is not None


class BaggageLogProcessorIncludeExcludeTest(unittest.TestCase):
    @staticmethod
    def _log_attributes(processor, baggage_keys):
        exporter = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(processor)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        token = attach(_baggage_context(baggage_keys))
        try:
            logger_provider.get_logger("test-logger").emit(None)
        finally:
            detach(token)
        logger_provider.force_flush()
        return dict(exporter.get_finished_logs()[-1].log_record.attributes)

    def test_include_exclude(self):
        for included, excluded, baggage_keys, expected in _INCLUDE_EXCLUDE_CASES:
            with self.subTest(included=included, excluded=excluded):
                attributes = self._log_attributes(
                    BaggageLogProcessor(included=included, excluded=excluded),
                    baggage_keys,
                )
                self.assertEqual(attributes, dict.fromkeys(expected, "value"))

    def test_no_arguments_copies_all_baggage(self):
        attributes = self._log_attributes(BaggageLogProcessor(), ["a", "b"])
        self.assertEqual(attributes, {"a": "value", "b": "value"})

    def test_max_baggage_attributes_with_include(self):
        attributes = self._log_attributes(
            BaggageLogProcessor(included=["key*"], max_baggage_attributes=2),
            ["other", "key1", "key2", "key3"],
        )
        self.assertEqual(attributes, {"key1": "value", "key2": "value"})

    def test_predicate_with_include_exclude_raises(self):
        for kwargs in ({"included": ["a"]}, {"excluded": ["a"]}, {"included": []}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    BaggageLogProcessor(ALLOW_ALL_BAGGAGE_KEYS, **kwargs)

    def test_entry_point(self):
        (entry_point,) = entry_points(group="opentelemetry_logs_processor", name="baggage")
        processor_class = entry_point.load()
        self.assertIs(processor_class, BaggageLogProcessor)
        attributes = self._log_attributes(
            processor_class(included=["a*"], excluded=["ab"]),
            ["a", "ab", "b"],
        )
        self.assertEqual(attributes, {"a": "value"})


if __name__ == "__main__":
    unittest.main()
