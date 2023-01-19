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

    def tearDown(self):
        super().tearDown()
        ThreadingInstrumentor().uninstrument()

    def test_thread_with_root(self):
        mock_wrap_start = mock.Mock()

        mock_threading = mock.Mock()

        wrap_start_result = 'wrap start result'

        mock_wrap_start.return_value = wrap_start_result

        mock_start_func = mock.Mock()

        mock_start_func.__name__ = 'start'

        setattr(mock_threading.Thread, 'start', mock_start_func)

        patch_wrap_start = mock.patch(
            'opentelemetry.instrumentation.threading.wrap_threading_start',
            mock_wrap_start)

        patch_threading = mock.patch(
            'opentelemetry.instrumentation.threading', mock_threading)

        with patch_wrap_start,   \
                patch_threading:
                ThreadingInstrumentor()

        self.assertEqual(
            getattr(mock_threading.Thread, 'start'), wrap_start_result)



