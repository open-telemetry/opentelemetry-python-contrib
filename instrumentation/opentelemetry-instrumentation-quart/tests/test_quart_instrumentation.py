# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# pylint: disable=invalid-name
import asyncio

import quart

from opentelemetry.instrumentation.quart import QuartInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.util._importlib_metadata import entry_points


class TestQuartInstrumentation(TestBase):
    def setUp(self):
        super().setUp()

        QuartInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
        )

    def tearDown(self):
        QuartInstrumentor().uninstrument()

        super().tearDown()

    def test_auto_instrumentation_creates_server_span(self):
        app = quart.Quart(__name__)

        @app.get("/users/<int:user_id>")
        async def user(user_id):
            return f"user {user_id}"

        async def make_request():
            response = await app.test_client().get("/users/123")
            assert response.status_code == 200

        asyncio.run(make_request())

        spans = self.memory_exporter.get_finished_spans()

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        self.assertEqual(len(server_spans), 1)

        server_span = server_spans[0]

        self.assertEqual(
            server_span.name,
            "GET /users/<int:user_id>",
        )

        self.assertEqual(
            server_span.attributes["http.route"],
            "/users/<int:user_id>",
        )

    def test_instrument_app(self):

        app = quart.Quart(__name__)

        QuartInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
        )

        @app.get("/users/<int:user_id>")
        async def user(user_id):
            return f"user {user_id}"

        async def make_request():
            response = await app.test_client().get("/users/123")
            assert response.status_code == 200

        asyncio.run(make_request())

        spans = self.memory_exporter.get_finished_spans()

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        self.assertEqual(len(server_spans), 1)

        self.assertEqual(
            server_spans[0].name,
            "GET /users/<int:user_id>",
        )

        self.assertEqual(
            server_spans[0].attributes["http.route"],
            "/users/<int:user_id>",
        )

    def test_uninstrument_app(self):
        app = quart.Quart(__name__)

        @app.get("/")
        async def index():
            return "ok"

        QuartInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
        )

        QuartInstrumentor.uninstrument_app(app)

        async def make_request():
            response = await app.test_client().get("/")
            assert response.status_code == 200

        asyncio.run(make_request())

        spans = self.memory_exporter.get_finished_spans()

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        self.assertEqual(len(server_spans), 0)

    def test_instrument_app_twice_does_not_duplicate_spans(self):
        app = quart.Quart(__name__)

        QuartInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
        )

        QuartInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
        )

        @app.get("/")
        async def index():
            return "ok"

        async def make_request():
            response = await app.test_client().get("/")
            assert response.status_code == 200

        asyncio.run(make_request())

        spans = self.memory_exporter.get_finished_spans()

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        self.assertEqual(len(server_spans), 1)

    def test_global_uninstrument_restores_quart(self):
        app = quart.Quart(__name__)

        @app.get("/")
        async def index():
            return "ok"

        QuartInstrumentor().uninstrument()

        async def make_request():
            response = await app.test_client().get("/")
            assert response.status_code == 200

        asyncio.run(make_request())

        spans = self.memory_exporter.get_finished_spans()

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        self.assertEqual(len(server_spans), 0)

    def test_entry_point(self):

        matching = [ep for ep in entry_points(group="opentelemetry_instrumentor") if ep.name == "quart"]

        self.assertEqual(len(matching), 1)

        instrumentor_class = matching[0].load()

        self.assertIs(
            instrumentor_class,
            QuartInstrumentor,
        )

    def test_missing_route_does_not_crash(self):
        app = quart.Quart(__name__)

        async def make_request():
            response = await app.test_client().get("/does-not-exist")
            assert response.status_code == 404

        asyncio.run(make_request())

        spans = self.memory_exporter.get_finished_spans()

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        self.assertEqual(len(server_spans), 1)

        self.assertEqual(
            server_spans[0].name,
            "GET /does-not-exist",
        )

        self.assertNotIn(
            "http.route",
            server_spans[0].attributes,
        )
