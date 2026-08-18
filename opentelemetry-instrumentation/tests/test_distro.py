# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

from unittest import TestCase

from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.util._importlib_metadata import EntryPoint


class MockInstrumetor(BaseInstrumentor):
    def instrumentation_dependencies(self):
        return []

    def _instrument(self, **kwargs):
        pass

    def _uninstrument(self, **kwargs):
        pass


class MockEntryPoint(EntryPoint):
    def __init__(self, name, value, group):  # pylint: disable=super-init-not-called
        pass

    def load(self, *args, **kwargs):  # pylint: disable=signature-differs
        return MockInstrumetor


class MockDistro(BaseDistro):
    def _configure(self, **kwargs):
        pass


class TestDistro(TestCase):
    def test_load_instrumentor(self):
        # pylint: disable=protected-access
        distro = MockDistro()

        instrumentor = MockInstrumetor()
        entry_point = MockEntryPoint(
            "MockInstrumetor",
            value="opentelemetry",
            group="opentelemetry_distro",
        )

        self.assertFalse(instrumentor._is_instrumented_by_opentelemetry)
        distro.load_instrumentor(entry_point)
        self.assertTrue(instrumentor._is_instrumented_by_opentelemetry)
