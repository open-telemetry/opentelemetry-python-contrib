# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import flask
from werkzeug.test import Client
from werkzeug.wrappers import Response

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase

# pylint: disable=import-error
from .base_test import InstrumentationTest


class TestAutomatic(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()

        FlaskInstrumentor().instrument()

        self.app = flask.Flask(__name__)

        self._common_initialization()

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FlaskInstrumentor().uninstrument()

    def test_uninstrument(self):
        # pylint: disable=access-member-before-definition
        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        FlaskInstrumentor().uninstrument()
        self.app = flask.Flask(__name__)

        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        self.client = Client(self.app, Response)

        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_exluded_urls_explicit(self):
        FlaskInstrumentor().uninstrument()
        FlaskInstrumentor().instrument(excluded_urls="/hello/456")

        self.app = flask.Flask(__name__)
        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        client = Client(self.app, Response)

        resp = client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        resp = client.get("/hello/456")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 456"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_no_op_tracer_provider(self):
        FlaskInstrumentor().uninstrument()
        FlaskInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        self.app = flask.Flask(__name__)
        self.app.route("/hello/<int:helloid>")(self._hello_endpoint)
        self.client = Client(self.app, Response)
        self.client.get("/hello/123")

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)
