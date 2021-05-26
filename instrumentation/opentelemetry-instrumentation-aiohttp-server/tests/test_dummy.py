
from aiohttp import web
from opentelemetry.instrumentation.aiohttp_server import _instrument_aiohttp_server
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

provider = TracerProvider()
processor = SimpleSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)


async def handler(request):
    return web.Response(text="hello")


app = web.Application()
app.add_routes([web.get('/', handler)])

_instrument_aiohttp_server()

web.run_app(app)
