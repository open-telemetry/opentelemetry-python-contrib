# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
import unittest

from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)


class TestLoggingHandlerRecursionGuard(unittest.TestCase):
    @staticmethod
    def _create_handler():
        exporter = InMemoryLogExporter()
        provider = LoggerProvider()
        provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
        handler = LoggingHandler(logger_provider=provider)
        return handler, exporter

    @staticmethod
    def _make_record(msg="test"):
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_recursive_emit_is_skipped(self):
        """Recursive emit() should be skipped to prevent deadlock.
        Regression test for https://github.com/open-telemetry/opentelemetry-python/issues/3858
        """
        handler, exporter = self._create_handler()
        token = handler._is_emitting.set(True)
        handler.emit(self._make_record("should be skipped"))
        self.assertEqual(len(exporter.get_finished_logs()), 0)
        handler._is_emitting.reset(token)

    def test_normal_emit_works(self):
        """Non-recursive emit() should process logs normally."""
        handler, exporter = self._create_handler()
        handler.emit(self._make_record("should be captured"))
        logs = exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].log_record.body, "should be captured")

    def test_is_emitting_resets_after_emit(self):
        """Context must reset after emit(), allowing subsequent logs."""
        handler, exporter = self._create_handler()
        handler.emit(self._make_record("first"))
        self.assertFalse(handler._is_emitting.get())
        handler.emit(self._make_record("second"))
        self.assertEqual(len(exporter.get_finished_logs()), 2)

    def test_is_emitting_is_isolated_across_threads(self):
        """Emit context on one thread must not block other threads."""
        handler, exporter = self._create_handler()
        token = handler._is_emitting.set(True)

        result = [False]

        def log_from_other_thread():
            handler.emit(self._make_record("from other thread"))
            result[0] = True

        thread = threading.Thread(target=log_from_other_thread)
        thread.start()
        thread.join(timeout=5)

        self.assertTrue(result[0], "Other thread should not be blocked")
        self.assertEqual(len(exporter.get_finished_logs()), 1)
        handler._is_emitting.reset(token)
