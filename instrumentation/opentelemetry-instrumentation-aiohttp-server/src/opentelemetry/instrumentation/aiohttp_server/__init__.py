import urllib
from aiohttp import web
from guillotina.utils import get_dotted_name
from multidict import CIMultiDictProxy
from opentelemetry import context, trace
from opentelemetry.instrumentation.aiohttp_server.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import http_status_to_status_code
from opentelemetry.propagate import extract
from opentelemetry.propagators.textmap import Getter
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.http import get_excluded_urls
from opentelemetry.util.http import remove_url_credentials

from typing import Tuple


_SUPPRESS_HTTP_INSTRUMENTATION_KEY = "suppress_http_instrumentation"

tracer = trace.get_tracer(__name__)
_excluded_urls = get_excluded_urls("FLASK")


def get_default_span_details(request: web.Request) -> Tuple[str, dict]:
    """Default implementation for get_default_span_details
    Args:
        scope: the asgi scope dictionary
    Returns:
        a tuple of the span name, and any attributes to attach to the span.
    """
    span_name = request.path.strip() or f"HTTP {request.method}"
    return span_name, {}


def _get_view_func(request) -> str:
    """TODO: is this only working for guillotina?"""
    try:
        return get_dotted_name(request.found_view)
    except AttributeError:
        return "unknown"


def collect_request_attributes(request: web.Request):
    """Collects HTTP request attributes from the ASGI scope and returns a
    dictionary to be used as span creation attributes."""

    server_host, port, http_url = (
        request.url.host,
        request.url.port,
        str(request.url),
    )
    query_string = request.query_string
    if query_string and http_url:
        if isinstance(query_string, bytes):
            query_string = query_string.decode("utf8")
        http_url += "?" + urllib.parse.unquote(query_string)

    result = {
        SpanAttributes.HTTP_SCHEME: request.scheme,
        SpanAttributes.HTTP_HOST: server_host,
        SpanAttributes.NET_HOST_PORT: port,
        SpanAttributes.HTTP_ROUTE: _get_view_func(request),
        SpanAttributes.HTTP_FLAVOR: f"{request.version.major}.{request.version.minor}",
        SpanAttributes.HTTP_TARGET: request.path,
        SpanAttributes.HTTP_URL: remove_url_credentials(http_url),
    }

    http_method = request.method
    if http_method:
        result[SpanAttributes.HTTP_METHOD] = http_method

    http_host_value_list = (
        [request.host] if type(request.host) != list else request.host
    )
    if http_host_value_list:
        result[SpanAttributes.HTTP_SERVER_NAME] = ",".join(
            http_host_value_list
        )
    http_user_agent = request.headers.get("user-agent")
    if http_user_agent:
        result[SpanAttributes.HTTP_USER_AGENT] = http_user_agent

    # remove None values
    result = {k: v for k, v in result.items() if v is not None}

    return result


def set_status_code(span, status_code):
    """Adds HTTP response attributes to span using the status_code argument."""
    if not span.is_recording():
        return
    try:
        status_code = int(status_code)
    except ValueError:
        span.set_status(
            Status(
                StatusCode.ERROR,
                "Non-integer HTTP status: " + repr(status_code),
            )
        )
    else:
        span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, status_code)
        span.set_status(
            Status(http_status_to_status_code(status_code, server_span=True))
        )


class AiohttpGetter(Getter):
    """Extract current trace from headers"""

    def get(self, carrier, key: str):
        """Getter implementation to retrieve a HTTP header value from the ASGI
        scope.

        Args:
            carrier: ASGI scope object
            key: header name in scope
        Returns:
            A list with a single string with the header value if it exists,
                else None.
        """
        headers: CIMultiDictProxy = carrier.headers
        if not headers:
            return None
        return headers.getall(key, None)

    def keys(self, carrier: dict):
        return list(carrier.keys())


getter = AiohttpGetter()


@web.middleware
async def middleware(request, handler):
    """Middleware for aiohttp implementing tracing logic"""
    if (
        context.get_value("suppress_instrumentation")
        or context.get_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY)
        or not _excluded_urls.url_disabled(request.url)
    ):
        return await handler(request)

    token = context.attach(extract(request, getter=getter))
    span_name, additional_attributes = get_default_span_details(request)

    with tracer.start_as_current_span(
        span_name,
        kind=trace.SpanKind.SERVER,
    ) as span:
        if span.is_recording():
            attributes = collect_request_attributes(request)
            attributes.update(additional_attributes)
            for key, value in attributes.items():
                span.set_attribute(key, value)
            try:
                resp = await handler(request)
                set_status_code(span, resp.status)
            finally:
                context.detach(token)
            return resp


class _InstrumentedApplication(web.Application):
    """Insert tracing middleware"""

    def __init__(self, *args, **kwargs):
        middlewares = kwargs.pop("middlewares", [])
        middlewares.insert(0, middleware)
        kwargs["middlewares"] = middlewares
        super().__init__(*args, **kwargs)


class AioHttpInstrumentor(BaseInstrumentor):
    # pylint: disable=protected-access,attribute-defined-outside-init
    """An instrumentor for aiohttp.web.Application

    See `BaseInstrumentor`
    """

    def _instrument(self, **kwargs):
        self._original_app = web.Application
        setattr(web, "Application", _InstrumentedApplication)

    def _uninstrument(self, **kwargs):
        setattr(web, "Application", self._original_app)

    def instrumentation_dependencies(self):
        return _instruments
