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


class TestThreadingInstrumentor(TestBase):
    # def setUp(self):
    #     super().setUp()
    #     ThreadingInstrumentor().instrument()

    #     self.tracer = get_tracer(__name__)

    def tearDown(self):
        super().tearDown()
        ThreadingInstrumentor().uninstrument()

    def test_thread_with_root(self):
        # Initialized the mock function for
        # opentelemetry.instrumentation.threading.wrap_threading_start
        mock_wrap_start = mock.Mock()

        # Initialized the mock function for
        # threading library imported in 
        # opentelemetry.instrumentation.threading 
        mock_threading = mock.Mock()

        #Sets variable for the return value for 
        # opentelemetry.instrumentation.threading.wrap_threading_start
        wrap_start_result = 'wrap start result'

        #Sets return value for 
        # opentelemetry.instrumentation.threading.wrap_threading_start
        mock_wrap_start.return_value = wrap_start_result

        #Initializes the mock function for threading.start
        mock_start_func = mock.Mock()

        #sets the name of the mock(threading.start) function
        mock_start_func.__name__ = 'start'
        
        #monkeypatches the mock_threading modules start function to the previoulyy created
        #mock of start function
        setattr(mock_threading.Thread, 'start', mock_start_func)

        #patches the opentelemetry.instrumentation.threading.wrap_threading_start
        patch_wrap_start = mock.patch(
            'opentelemetry.instrumentation.threading.wrap_threading_start',
            mock_wrap_start)
        # patches the opentelemetry.instrumentation.threading.threading
        patch_threading = mock.patch(
        'opentelemetry.instrumentation.threading', mock_threading)
        
        #using the above two patches created, it calls the threadingInstrumentor class
        with patch_wrap_start, patch_threading:
            ThreadingInstrumentor().instrument()
        print("********************************")
        # print(mock_threading.Thread.start())

        #checks if mock_wrap_start was called
        self.assertFalse(mock_wrap_start.called)
        self.assertEqual(
            getattr(mock_threading.Thread, 'start'), wrap_start_result)
