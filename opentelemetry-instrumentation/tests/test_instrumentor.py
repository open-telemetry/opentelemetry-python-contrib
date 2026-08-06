# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from logging import WARNING
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.instrumentation.dependencies import (
    DependencyConflict,
    DependencyConflictError,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


class TestInstrumentor(TestCase):
    class Instrumentor(BaseInstrumentor):
        def _instrument(self, **kwargs):
            return "instrumented"

        def _uninstrument(self, **kwargs):
            return "uninstrumented"

        def instrumentation_dependencies(self):
            return []

    def test_protect(self):
        instrumentor = self.Instrumentor()

        with self.assertLogs(level=WARNING):
            self.assertIs(instrumentor.uninstrument(), None)

        self.assertEqual(instrumentor.instrument(), "instrumented")

        with self.assertLogs(level=WARNING):
            self.assertIs(instrumentor.instrument(), None)

        self.assertEqual(instrumentor.uninstrument(), "uninstrumented")

        with self.assertLogs(level=WARNING):
            self.assertIs(instrumentor.uninstrument(), None)

    def test_singleton(self):
        self.assertIs(self.Instrumentor(), self.Instrumentor())

    @patch("opentelemetry.instrumentation.instrumentor._LOG")
    @patch(
        "opentelemetry.instrumentation.instrumentor.BaseInstrumentor._check_dependency_conflicts"
    )
    def test_instrument_missing_dependency_raise(
        self, mock__check_dependency_conflicts, mock_logger
    ):
        instrumentor = self.Instrumentor()

        mock__check_dependency_conflicts.return_value = DependencyConflict(
            "missing", "missing"
        )

        self.assertRaises(
            DependencyConflictError,
            instrumentor.instrument,
            raise_exception_on_conflict=True,
        )
        mock_logger.error.assert_not_called()

    @patch("opentelemetry.instrumentation.instrumentor._LOG")
    @patch(
        "opentelemetry.instrumentation.instrumentor.BaseInstrumentor._check_dependency_conflicts"
    )
    def test_instrument_missing_dependency_log_error(
        self, mock__check_dependency_conflicts, mock_logger
    ):
        instrumentor = self.Instrumentor()
        conflict = DependencyConflict("missing", "missing")
        mock__check_dependency_conflicts.return_value = conflict
        self.assertIsNone(
            instrumentor.instrument(raise_exception_on_conflict=False)
        )
        mock_logger.error.assert_any_call(conflict)
