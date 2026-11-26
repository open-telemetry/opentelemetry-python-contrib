# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from contextlib import ExitStack
from os import environ
from unittest.mock import patch

import flask

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.test.wsgitestutil import WsgiTestBase

_FLASK_EXCLUDED_URLS = "OTEL_PYTHON_FLASK_EXCLUDED_URLS"
_GLOBAL_EXCLUDED_URLS = "OTEL_PYTHON_EXCLUDED_URLS"


class TestExcludedUrls(WsgiTestBase):
    def test_excluded_urls_resolved_at_setup(self) -> None:
        cases = (
            (
                "Flask environment takes precedence",
                {_FLASK_EXCLUDED_URLS: "/healthz", _GLOBAL_EXCLUDED_URLS: "/readyz"},
                None,
                ["GET /readyz"],
            ),
            (
                "global environment fallback",
                {_GLOBAL_EXCLUDED_URLS: "/healthz"},
                None,
                ["GET /readyz"],
            ),
            (
                "explicit argument overrides environment",
                {_FLASK_EXCLUDED_URLS: "/healthz", _GLOBAL_EXCLUDED_URLS: "/healthz"},
                "/readyz",
                ["GET /healthz"],
            ),
            (
                "explicit empty argument overrides environment",
                {_FLASK_EXCLUDED_URLS: "/healthz", _GLOBAL_EXCLUDED_URLS: "/readyz"},
                "",
                ["GET /healthz", "GET /readyz"],
            ),
        )
        for automatic in (True, False):
            for case, environment, excluded_urls, expected in cases:
                with self.subTest(automatic=automatic, case=case):
                    self._assert_traced_routes(automatic, environment, excluded_urls, expected)

    def _assert_traced_routes(
        self,
        automatic: bool,
        environment: dict[str, str],
        excluded_urls: str | None,
        expected: list[str],
    ) -> None:
        self.memory_exporter.clear()
        updated_exclusions = "/healthz,/readyz"
        instrumentor = FlaskInstrumentor()
        with patch.dict(environ), ExitStack() as cleanup:
            environ.pop(_FLASK_EXCLUDED_URLS, None)
            environ.pop(_GLOBAL_EXCLUDED_URLS, None)
            environ.update(environment)

            if automatic:
                instrumentor.instrument(excluded_urls=excluded_urls)
                cleanup.callback(instrumentor.uninstrument)
                environ[_FLASK_EXCLUDED_URLS] = updated_exclusions

            app = flask.Flask(__name__)
            if not automatic:
                instrumentor.instrument_app(app, excluded_urls=excluded_urls)
                cleanup.callback(instrumentor.uninstrument_app, app)
                environ[_FLASK_EXCLUDED_URLS] = updated_exclusions

            app.add_url_rule("/healthz", "healthz", lambda: "ok")
            app.add_url_rule("/readyz", "readyz", lambda: "ok")
            client = app.test_client()
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertEqual(client.get("/readyz").status_code, 200)
            self.assertEqual([span.name for span in self.memory_exporter.get_finished_spans()], expected)
