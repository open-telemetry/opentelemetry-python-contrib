# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase

from .base_test import InstrumentationTest


class TestCopyContext(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()
        FlaskInstrumentor().instrument()
        self.app = flask.Flask(__name__)
        self._common_initialization()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FlaskInstrumentor().uninstrument()

    def test_copycontext(self):
        """Test that instrumentation tear down does not blow up
        when the request calls functions where the context has been
        copied via `flask.copy_current_request_context`
        """
        self.app = flask.Flask(__name__)
        self.app.route("/copy_context")(self._copy_context_endpoint)
        client = Client(self.app, Response)
        resp = client.get("/copy_context", headers={"x-req": "a-header"})

        self.assertEqual(200, resp.status_code)
        self.assertEqual("GET /copy_context", resp.json["span_name"])
        self.assertEqual("a-header", resp.json["request_header"])
