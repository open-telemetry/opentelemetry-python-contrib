from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from opentelemetry.instrumentation.aiohttp_server import (
    AioHttpServerInstrumentor,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase


class TestCase(AioHTTPTestCase, TestBase):
    async def get_application(self) -> web.Application:
        routes = web.RouteTableDef()

        @routes.get("/status/{status}")
        async def status(request):
            return web.Response(status=request.match_info["status"])

        @routes.post("/post")
        async def post(_):
            return web.Response()

        app = web.Application()
        app.add_routes(routes)

        return app

    def setUp(self):
        super().setUp()
        self.memory_exporter.clear()
        self.instrumentor = AioHttpServerInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self) -> None:
        super().tearDown()
        self.instrumentor.uninstrument()

    @property
    def first_span(self):
        return self.memory_exporter.get_finished_spans()[0]


class TestAioHttpServerInstrumentor(TestCase):
    @unittest_run_loop
    async def test_instrumention_is_operational(self):
        await self.client.request("GET", "/status/200")

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    @unittest_run_loop
    async def test_status_code_attribute(self):
        await self.client.request("GET", "/status/405")

        self.assert_span_has_attributes(
            self.first_span, {SpanAttributes.HTTP_STATUS_CODE: 405}
        )

    @unittest_run_loop
    async def test_default_span_name_GET(self):
        await self.client.request("GET", "/status/200")

        self.assertEqual(self.first_span.name, "HTTP GET")

    @unittest_run_loop
    async def test_default_span_name_POST(self):
        await self.client.request("POST", "/post")

        self.assertEqual(self.first_span.name, "HTTP POST")
