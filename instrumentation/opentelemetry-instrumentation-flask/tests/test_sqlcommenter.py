# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase

# pylint: disable=import-error
from .base_test import InstrumentationTest


class TestSQLCommenter(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()
        FlaskInstrumentor().instrument()
        self.app = flask.Flask(__name__)
        self._common_initialization()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FlaskInstrumentor().uninstrument()

    def test_sqlcommenter_enabled_default(self):
        self.app = flask.Flask(__name__)
        self.app.route("/sqlcommenter")(self._sqlcommenter_endpoint)
        client = Client(self.app, Response)

        resp = client.get("/sqlcommenter")
        self.assertEqual(200, resp.status_code)
        self.assertRegex(
            list(resp.response)[0].strip(),
            b'{"controller":"_sqlcommenter_endpoint","framework":"flask:(.*)","route":"/sqlcommenter"}',
        )

    def test_sqlcommenter_enabled_with_configurations(self):
        FlaskInstrumentor().uninstrument()
        FlaskInstrumentor().instrument(
            enable_commenter=True, commenter_options={"route": False}
        )

        self.app = flask.Flask(__name__)
        self.app.route("/sqlcommenter")(self._sqlcommenter_endpoint)
        client = Client(self.app, Response)

        resp = client.get("/sqlcommenter")
        self.assertEqual(200, resp.status_code)
        self.assertRegex(
            list(resp.response)[0].strip(),
            b'{"controller":"_sqlcommenter_endpoint","framework":"flask:(.*)"}',
        )

    def test_sqlcommenter_disabled(self):
        FlaskInstrumentor().uninstrument()
        FlaskInstrumentor().instrument(enable_commenter=False)

        self.app = flask.Flask(__name__)
        self.app.route("/sqlcommenter")(self._sqlcommenter_endpoint)
        client = Client(self.app, Response)

        resp = client.get("/sqlcommenter")
        self.assertEqual(200, resp.status_code)
        self.assertEqual(list(resp.response)[0].strip(), b"{}")
