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
import threading
from unittest import mock

from packaging import version

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

#TEST_DIR = os.path.dirname(os.path.realpath(__file__))
#TEST_DIR = os.path.join(TEST_DIR, "templates")


class TestThreadingInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        ThreadingInstrumentor().instrument()

        self.tracer = get_tracer(__name__)

    #def tearDown(self):
        #super().tearDown()
        #ThreadingInstrumentor().uninstrument()

    def test_thread_with_root(self):
        with self.tracer.start_As_current_span("root"):
            t1 = threading.Thread.start_func()
            self.assertEqual(t1.__dict__, "")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        #pylint:disable = unbalanced-tuple-unpacking
        render, template, root = spans[:3]
        self.assertIs(render.parent, root.get_span_context())
        self.assertIs(template.parent, root.get_span_context())
        self.assertIsNone(root.parent)



