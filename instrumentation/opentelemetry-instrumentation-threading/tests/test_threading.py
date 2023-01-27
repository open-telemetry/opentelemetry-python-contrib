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
from opentelemetry.trace import SpanKind, get_tracer



class TestThreadingInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        ThreadingInstrumentor().instrument()

        self.tracer = get_tracer(__name__)

    def tearDown(self):
        super().tearDown()
        # ThreadingInstrumentor().uninstrument()
    def print_square(self, num):
        print("Square: {}" .format(num * num))

    def test_thread_with_root(self):
       
        t1 = threading.Thread(target=self.print_square, args=(10))
        t1.start()
        t1.join()
           
        spans = self.memory_exporter.get_finished_spans()
        
        print(spans[0].__dict__)
        print(spans[1].__dict__)
        self.assertEqual(len(spans), 3)