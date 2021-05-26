import functools
import typing as t

from aiohttp.web import (
    RequestHandler,
    StreamResponse,
    BaseRequest,
)
from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import http_status_to_status_code
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.util.http import (
    ExcludeList,
    get_excluded_urls,
    get_traced_request_attrs,
)

from .version import __version__

RequestHook = t.Callable[[trace.Span, BaseRequest], t.Any]
ResponseHook = t.Callable[[trace.Span, BaseRequest, StreamResponse], t.Any]


_CONFIG_PREFIX = "AIOHTTP_SERVER"
_CONFIG_TRACED_ATTRS = get_traced_request_attrs(_CONFIG_PREFIX)
_CONFIG_EXCLUDED_URLS = get_excluded_urls(_CONFIG_PREFIX)
_SPAN_KEY = "opentelemetry-instrumentor-aiohttp-server.span_key"


def _span_name(request: BaseRequest) -> str:
    return f"HTTP {request.method.upper()}"


def _set_http_attributes(span: trace.Span, request: BaseRequest):
    if not span.is_recording():
        return

    span.set_attribute(SpanAttributes.HTTP_METHOD, request.method.upper())
    span.set_attribute(SpanAttributes.HTTP_URL, str(request.url))
    span.set_attribute(
        SpanAttributes.HTTP_FLAVOR, ".".join(map(str, request.version))
    )


def _set_span_status(span: trace.Span, response: StreamResponse):
    if not span.is_recording():
        return

    reason = None
    try:
        http_status = int(response.status)
    except ValueError:
        http_status = response.status
        reason = f"Unable to parse status code: {http_status!r}"
    except AttributeError:
        reason = f"Response without a status code"

    if reason:
        span.set_status(trace.Status(trace.StatusCode.ERROR), reason=reason)
    else:
        span.set_status(trace.Status(http_status_to_status_code(http_status)))
        span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, http_status)


def _instrument_aiohttp_server(
    *,
    excluded_urls: t.Iterable[str] = (),
    request_hook: t.Optional[RequestHook] = None,
    response_hook: t.Optional[ResponseHook] = None,
    tracer_provider: t.Optional[trace.TracerProvider] = None,
):
    _handle_request_wrapped = RequestHandler._handle_request

    @functools.wraps(_handle_request_wrapped)
    async def _handle_request_wrapper(
        self, request: BaseRequest, start_time: float,
    ):
        token = context.attach(propagate.extract(request.headers))

        tracer = trace.get_tracer(__name__, __version__, tracer_provider)
        span = tracer.start_span(
            _span_name(request), kind=trace.SpanKind.SERVER,
        )
        _set_http_attributes(span, request)

        try:
            if request_hook:
                request_hook(span, request)

            with trace.use_span(
                span,
                end_on_exit=False,
                record_exception=False,
                set_status_on_exception=False,
            ):
                request[_SPAN_KEY] = span
                response, reset = await _handle_request_wrapped(
                    self, request, start_time
                )

            _set_span_status(span, response)

            if response_hook:
                response_hook(span, request, response)

            return response, reset
        finally:
            span.end()
            context.detach(token)

    RequestHandler._handle_request = _handle_request_wrapper

    handle_error_wrapped = RequestHandler.handle_error

    @functools.wraps(handle_error_wrapped)
    def handle_error_wrapper(
        self,
        request: BaseRequest,
        status: int = 500,
        exc: t.Optional[BaseException] = None,
        message: t.Optional[str] = None,
    ) -> StreamResponse:
        span = request.get(_SPAN_KEY)
        if span and span.is_recording() and exc:
            span.record_exception(exc)

        return handle_error_wrapped(self, request, status, exc, message)

    RequestHandler.handle_error = handle_error_wrapper


class AioHttpServerInstrumentor(BaseInstrumentor):
    def _uninstrument(self, **kwargs):
        pass

    def _instrument(self, **kwargs):
        pass

    def instrument_app(self):
        pass
