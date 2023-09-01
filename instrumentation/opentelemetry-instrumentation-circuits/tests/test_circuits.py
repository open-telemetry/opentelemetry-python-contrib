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

import os

from circuits import Component, Event

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.circuits import CircuitsInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
TMPL_DIR = os.path.join(TEST_DIR, "templates")


class TestCircuitsInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        CircuitsInstrumentor().instrument()

        self.tracer = get_tracer(__name__)

    def tearDown(self):
        super().tearDown()
        CircuitsInstrumentor().uninstrument()

    def test_demo_script(self):
        with self.tracer.start_as_current_span("root"):

            class hello(Event):
                """hello Event"""

            class App(Component):
                def hello(self):
                    print("Hello World!")

                def started(self, component):
                    self.fire(hello())
                    self.stop()

            App().run()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 7)

        self.assertEqual(
            [span.name for span in spans],
            [
                "circuits.Manager.tick",
                "circuits.Manager.tick",
                "circuits.Manager.tick",
                "circuits.Manager.tick",
                "circuits.Manager.tick",
                "circuits.Manager.tick",
                "root",
            ],
        )
        self.assertIsNone(spans[6].parent)
