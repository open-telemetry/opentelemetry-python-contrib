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

import flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase

# pylint: disable=import-error
from .base_test import InstrumentationTest


class TestMultiThreading(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()
        FlaskInstrumentor().instrument()
        self.app = flask.Flask(__name__)
        self._common_initialization()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FlaskInstrumentor().uninstrument()

    def test_multithreaded(self):
        """Test that instrumentation tear down does not blow up
        when the request thread spawn children threads and the request
        context is copied to the children threads
        """
        self.app = flask.Flask(__name__)
        self.app.route("/multithreaded/<int:count>")(
            self._multithreaded_endpoint
        )
        client = Client(self.app, Response)
        count = 5
        resp = client.get(f"/multithreaded/{count}")
        self.assertEqual(200, resp.status_code)
        # Should return the specified number of random integers
        self.assertEqual(count, len(resp.text.split(" ")))
