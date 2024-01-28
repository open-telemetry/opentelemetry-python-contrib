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
# type: ignore

from unittest import TestCase,mock

from importlib_metadata import EntryPoint

from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


class MockInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self):
        return []

    def _instrument(self, **kwargs):
        pass

    def _uninstrument(self, **kwargs):
        pass


class MockEntryPoint(EntryPoint):
    def __init__(self, obj):  # pylint: disable=super-init-not-called
        self._obj = obj

    def load(self, *args, **kwargs):  # pylint: disable=signature-differs
        return self._obj


class MockDistro(BaseDistro):
    def _configure(self, **kwargs):
        pass


class TestDistro(TestCase):
    def test_load_instrumentor(self):
        distro = MockDistro()

        # Create an instance of MockInstrumentor
        instrumentor_instance = MockInstrumentor()

        # Create a mock EntryPoint. The load method should return a callable 
        # that returns the instrumentor instance
        mock_entry_point = mock.Mock()
        mock_entry_point.load.return_value = lambda: instrumentor_instance

        self.assertFalse(instrumentor_instance._is_instrumented_by_opentelemetry)
        
        # Use the mock entry point in your test
        distro.load_instrumentor(mock_entry_point)

        self.assertTrue(instrumentor_instance._is_instrumented_by_opentelemetry)
