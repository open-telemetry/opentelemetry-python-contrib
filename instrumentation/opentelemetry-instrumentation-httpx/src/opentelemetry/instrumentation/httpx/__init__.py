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
"""
Usage
-----

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace requests.

.. code-block:: python

     import httpx
     from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

     url = "https://some.url/get"
     HTTPXClientInstrumentor().instrument()

     with httpx.Client() as client:
          response = client.get(url)

     async with httpx.AsyncClient() as client:
          response = await client.get(url)

Instrumenting single clients
****************************

If you only want to instrument requests for specific client instances, you can
use the `instrument_client` method.


.. code-block:: python

    import httpx
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    url = "https://some.url/get"

    with httpx.Client(transport=telemetry_transport) as client:
        HTTPXClientInstrumentor.instrument_client(client)
        response = client.get(url)

    async with httpx.AsyncClient(transport=telemetry_transport) as client:
        HTTPXClientInstrumentor.instrument_client(client)
        response = await client.get(url)


Uninstrument
************

If you need to uninstrument clients, there are two options available.

.. code-block:: python

     import httpx
     from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

     HTTPXClientInstrumentor().instrument()
     client = httpx.Client()

     # Uninstrument a specific client
     HTTPXClientInstrumentor.uninstrument_client(client)

     # Uninstrument all clients
     HTTPXClientInstrumentor().uninstrument()


Using transports directly
*************************

If you don't want to use the instrumentor class, you can use the transport classes directly.


.. code-block:: python

    import httpx
    from opentelemetry.instrumentation.httpx import (
        AsyncOpenTelemetryTransport,
        SyncOpenTelemetryTransport,
    )

    url = "https://some.url/get"
    transport = httpx.HTTPTransport()
    telemetry_transport = SyncOpenTelemetryTransport(transport)

    with httpx.Client(transport=telemetry_transport) as client:
        response = client.get(url)

    transport = httpx.AsyncHTTPTransport()
    telemetry_transport = AsyncOpenTelemetryTransport(transport)

    async with httpx.AsyncClient(transport=telemetry_transport) as client:
        response = await client.get(url)


Request and response hooks
***************************

The instrumentation supports specifying request and response hooks. These are functions that get called back by the instrumentation right after a span is created for a request
and right before the span is finished while processing a response.

.. note::

    The request hook receives the raw arguments provided to the transport layer. The response hook receives the raw return values from the transport layer.

The hooks can be configured as follows:


.. code-block:: python

    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    def request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    def response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    async def async_request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    async def async_response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    HTTPXClientInstrumentor().instrument(
        request_hook=request_hook,
        response_hook=response_hook,
        async_request_hook=async_request_hook,
        async_response_hook=async_response_hook
    )


Or if you are using the transport classes directly:


.. code-block:: python

    from opentelemetry.instrumentation.httpx import SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport

    def request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    def response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    async def async_request_hook(span, request):
        # method, url, headers, stream, extensions = request
        pass

    async def async_response_hook(span, request, response):
        # method, url, headers, stream, extensions = request
        # status_code, headers, stream, extensions = response
        pass

    transport = httpx.HTTPTransport()
    telemetry_transport = SyncOpenTelemetryTransport(
        transport,
        request_hook=request_hook,
        response_hook=response_hook
    )

    async_transport = httpx.AsyncHTTPTransport()
    async_telemetry_transport = AsyncOpenTelemetryTransport(
        async_transport,
        request_hook=async_request_hook,
        response_hook=async_response_hook
    )

API
---
"""
import logging
import typing
from asyncio import iscoroutinefunction
from types import TracebackType

import httpx

from opentelemetry.instrumentation._semconv import (
    _get_schema_url,
    _HTTPStabilityMode,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _set_http_host_client,
    _set_http_method,
    _set_http_network_protocol_version,
    _set_http_peer_port_client,
    _set_http_status_code,
    _set_http_url,
)
from opentelemetry.instrumentation.httpx.package import _instruments
from opentelemetry.instrumentation.httpx.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    http_status_to_status_code,
    is_http_instrumentation_enabled,
)
from opentelemetry.propagate import inject
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
)
from opentelemetry.trace import SpanKind, TracerProvider, get_tracer
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.http import remove_url_credentials, sanitize_method

_logger = logging.getLogger(__name__)

URL = typing.Tuple[bytes, bytes, typing.Optional[int], bytes]
Headers = typing.List[typing.Tuple[bytes, bytes]]
RequestHook = typing.Callable[[Span, "RequestInfo"], None]
ResponseHook = typing.Callable[[Span, "RequestInfo", "ResponseInfo"], None]
AsyncRequestHook = typing.Callable[
    [Span, "RequestInfo"], typing.Awaitable[typing.Any]
]
AsyncResponseHook = typing.Callable[
    [Span, "RequestInfo", "ResponseInfo"], typing.Awaitable[typing.Any]
]


class RequestInfo(typing.NamedTuple):
    method: bytes
    url: URL
    headers: typing.Optional[Headers]
    stream: typing.Optional[
        typing.Union[httpx.SyncByteStream, httpx.AsyncByteStream]
    ]
    extensions: typing.Optional[dict]


class ResponseInfo(typing.NamedTuple):
    status_code: int
    headers: typing.Optional[Headers]
    stream: typing.Iterable[bytes]
    extensions: typing.Optional[dict]


def _get_default_span_name(method: str) -> str:
    method = sanitize_method(method.strip())
    if method == "_OTHER":
        method = "HTTP"

    return method


def _prepare_headers(headers: typing.Optional[Headers]) -> httpx.Headers:
    return httpx.Headers(headers)


def _extract_parameters(args, kwargs):
    if isinstance(args[0], httpx.Request):
        # In httpx >= 0.20.0, handle_request receives a Request object
        request: httpx.Request = args[0]
        method = request.method.encode()
        url = httpx.URL(remove_url_credentials(str(request.url)))
        headers = request.headers
        stream = request.stream
        extensions = request.extensions
    else:
        # In httpx < 0.20.0, handle_request receives the parameters separately
        method = args[0]
        url = args[1]
        headers = kwargs.get("headers", args[2] if len(args) > 2 else None)
        stream = kwargs.get("stream", args[3] if len(args) > 3 else None)
        extensions = kwargs.get(
            "extensions", args[4] if len(args) > 4 else None
        )

    return method, url, headers, stream, extensions


def _inject_propagation_headers(headers, args, kwargs):
    _headers = _prepare_headers(headers)
    inject(_headers)
    if isinstance(args[0], httpx.Request):
        request: httpx.Request = args[0]
        request.headers = _headers
    else:
        kwargs["headers"] = _headers.raw


def _extract_response(
    response: typing.Union[
        httpx.Response, typing.Tuple[int, Headers, httpx.SyncByteStream, dict]
    ]
) -> typing.Tuple[int, Headers, httpx.SyncByteStream, dict, str]:
    if isinstance(response, httpx.Response):
        status_code = response.status_code
        headers = response.headers
        stream = response.stream
        extensions = response.extensions
        http_version = response.http_version
    else:
        status_code, headers, stream, extensions = response
        http_version = extensions.get("http_version", b"HTTP/1.1").decode(
            "ascii", errors="ignore"
        )

    return (status_code, headers, stream, extensions, http_version)


def _apply_request_client_attributes_to_span(
    span_attributes: dict,
    url: typing.Union[str, URL, httpx.URL],
    method_original: str,
    semconv: _HTTPStabilityMode,
):
    url = httpx.URL(url)
    # http semconv transition: http.method -> http.request.method
    _set_http_method(
        span_attributes,
        method_original,
        sanitize_method(method_original),
        semconv,
    )
    # http semconv transition: http.url -> url.full
    _set_http_url(span_attributes, str(url), semconv)

    if _report_new(semconv):
        if url.host:
            # http semconv transition: http.host -> server.address
            _set_http_host_client(span_attributes, url.host, semconv)
            # http semconv transition: net.sock.peer.addr -> network.peer.address
            span_attributes[NETWORK_PEER_ADDRESS] = url.host
        if url.port:
            # http semconv transition: net.sock.peer.port -> network.peer.port
            _set_http_peer_port_client(span_attributes, url.port, semconv)
            span_attributes[NETWORK_PEER_PORT] = url.port


def _apply_response_client_attributes_to_span(
    span: Span,
    status_code: int,
    http_version: str,
    semconv: _HTTPStabilityMode,
):
    # http semconv transition: http.status_code -> http.response.status_code
    # TODO: use _set_status when it's stable for http clients
    span_attributes = {}
    _set_http_status_code(
        span_attributes,
        status_code,
        semconv,
    )
    http_status_code = http_status_to_status_code(status_code)
    span.set_status(http_status_code)

    if http_status_code == StatusCode.ERROR and _report_new(semconv):
        # http semconv transition: new error.type
        span_attributes[ERROR_TYPE] = str(status_code)

    if http_version and _report_new(semconv):
        # http semconv transition: http.flavor -> network.protocol.version
        _set_http_network_protocol_version(
            span_attributes,
            http_version.replace("HTTP/", ""),
            semconv,
        )

    for key, val in span_attributes.items():
        span.set_attribute(key, val)


class SyncOpenTelemetryTransport(httpx.BaseTransport):
    """Sync transport class that will trace all requests made with a client.

    Args:
        transport: SyncHTTPTransport instance to wrap
        tracer_provider: Tracer provider to use
        request_hook: A hook that receives the span and request that is called
            right after the span is created
        response_hook: A hook that receives the span, request, and response
            that is called right before the span ends
    """

    def __init__(
        self,
        transport: httpx.BaseTransport,
        tracer_provider: typing.Optional[TracerProvider] = None,
        request_hook: typing.Optional[RequestHook] = None,
        response_hook: typing.Optional[ResponseHook] = None,
    ):
        _OpenTelemetrySemanticConventionStability._initialize()
        self._sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP,
        )

        self._transport = transport
        self._tracer = get_tracer(
            __name__,
            instrumenting_library_version=__version__,
            tracer_provider=tracer_provider,
            schema_url=_get_schema_url(self._sem_conv_opt_in_mode),
        )
        self._request_hook = request_hook
        self._response_hook = response_hook

    def __enter__(self) -> "SyncOpenTelemetryTransport":
        self._transport.__enter__()
        return self

    def __exit__(
        self,
        exc_type: typing.Optional[typing.Type[BaseException]] = None,
        exc_value: typing.Optional[BaseException] = None,
        traceback: typing.Optional[TracebackType] = None,
    ) -> None:
        self._transport.__exit__(exc_type, exc_value, traceback)

    # pylint: disable=R0914
    def handle_request(
        self,
        *args,
        **kwargs,
    ) -> typing.Union[
        typing.Tuple[int, "Headers", httpx.SyncByteStream, dict],
        httpx.Response,
    ]:
        """Add request info to span."""
        if not is_http_instrumentation_enabled():
            return self._transport.handle_request(*args, **kwargs)

        method, url, headers, stream, extensions = _extract_parameters(
            args, kwargs
        )
        method_original = method.decode()
        span_name = _get_default_span_name(method_original)
        span_attributes = {}
        # apply http client response attributes according to semconv
        _apply_request_client_attributes_to_span(
            span_attributes,
            url,
            method_original,
            self._sem_conv_opt_in_mode,
        )

        request_info = RequestInfo(method, url, headers, stream, extensions)

        with self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            exception = None
            if callable(self._request_hook):
                self._request_hook(span, request_info)

            _inject_propagation_headers(headers, args, kwargs)

            try:
                response = self._transport.handle_request(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                response = getattr(exc, "response", None)

            if isinstance(response, (httpx.Response, tuple)):
                status_code, headers, stream, extensions, http_version = (
                    _extract_response(response)
                )

                if span.is_recording():
                    # apply http client response attributes according to semconv
                    _apply_response_client_attributes_to_span(
                        span,
                        status_code,
                        http_version,
                        self._sem_conv_opt_in_mode,
                    )
                if callable(self._response_hook):
                    self._response_hook(
                        span,
                        request_info,
                        ResponseInfo(status_code, headers, stream, extensions),
                    )

            if exception:
                if span.is_recording() and _report_new(
                    self._sem_conv_opt_in_mode
                ):
                    span.set_attribute(
                        ERROR_TYPE, type(exception).__qualname__
                    )
                raise exception.with_traceback(exception.__traceback__)

        return response

    def close(self) -> None:
        self._transport.close()


class AsyncOpenTelemetryTransport(httpx.AsyncBaseTransport):
    """Async transport class that will trace all requests made with a client.

    Args:
        transport: AsyncHTTPTransport instance to wrap
        tracer_provider: Tracer provider to use
        request_hook: A hook that receives the span and request that is called
            right after the span is created
        response_hook: A hook that receives the span, request, and response
            that is called right before the span ends
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        tracer_provider: typing.Optional[TracerProvider] = None,
        request_hook: typing.Optional[AsyncRequestHook] = None,
        response_hook: typing.Optional[AsyncResponseHook] = None,
    ):
        _OpenTelemetrySemanticConventionStability._initialize()
        self._sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.HTTP,
        )

        self._transport = transport
        self._tracer = get_tracer(
            __name__,
            instrumenting_library_version=__version__,
            tracer_provider=tracer_provider,
            schema_url=_get_schema_url(self._sem_conv_opt_in_mode),
        )
        self._request_hook = request_hook
        self._response_hook = response_hook

    async def __aenter__(self) -> "AsyncOpenTelemetryTransport":
        await self._transport.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[typing.Type[BaseException]] = None,
        exc_value: typing.Optional[BaseException] = None,
        traceback: typing.Optional[TracebackType] = None,
    ) -> None:
        await self._transport.__aexit__(exc_type, exc_value, traceback)

    # pylint: disable=R0914
    async def handle_async_request(self, *args, **kwargs) -> typing.Union[
        typing.Tuple[int, "Headers", httpx.AsyncByteStream, dict],
        httpx.Response,
    ]:
        """Add request info to span."""
        if not is_http_instrumentation_enabled():
            return await self._transport.handle_async_request(*args, **kwargs)

        method, url, headers, stream, extensions = _extract_parameters(
            args, kwargs
        )
        method_original = method.decode()
        span_name = _get_default_span_name(method_original)
        span_attributes = {}
        # apply http client response attributes according to semconv
        _apply_request_client_attributes_to_span(
            span_attributes,
            url,
            method_original,
            self._sem_conv_opt_in_mode,
        )

        request_info = RequestInfo(method, url, headers, stream, extensions)

        with self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            exception = None
            if callable(self._request_hook):
                await self._request_hook(span, request_info)

            _inject_propagation_headers(headers, args, kwargs)

            try:
                response = await self._transport.handle_async_request(
                    *args, **kwargs
                )
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                response = getattr(exc, "response", None)

            if isinstance(response, (httpx.Response, tuple)):
                status_code, headers, stream, extensions, http_version = (
                    _extract_response(response)
                )

                if span.is_recording():
                    # apply http client response attributes according to semconv
                    _apply_response_client_attributes_to_span(
                        span,
                        status_code,
                        http_version,
                        self._sem_conv_opt_in_mode,
                    )

                if callable(self._response_hook):
                    await self._response_hook(
                        span,
                        request_info,
                        ResponseInfo(status_code, headers, stream, extensions),
                    )

            if exception:
                if span.is_recording() and _report_new(
                    self._sem_conv_opt_in_mode
                ):
                    span.set_attribute(
                        ERROR_TYPE, type(exception).__qualname__
                    )
                raise exception.with_traceback(exception.__traceback__)

        return response

    async def aclose(self) -> None:
        await self._transport.aclose()


class _InstrumentedClient(httpx.Client):
    _tracer_provider = None
    _request_hook = None
    _response_hook = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._original_transport = self._transport
        self._original_mounts = self._mounts.copy()
        self._is_instrumented_by_opentelemetry = True

        self._transport = SyncOpenTelemetryTransport(
            self._transport,
            tracer_provider=_InstrumentedClient._tracer_provider,
            request_hook=_InstrumentedClient._request_hook,
            response_hook=_InstrumentedClient._response_hook,
        )
        self._mounts.update(
            {
                url_pattern: (
                    SyncOpenTelemetryTransport(
                        transport,
                        tracer_provider=_InstrumentedClient._tracer_provider,
                        request_hook=_InstrumentedClient._request_hook,
                        response_hook=_InstrumentedClient._response_hook,
                    )
                    if transport is not None
                    else transport
                )
                for url_pattern, transport in self._original_mounts.items()
            }
        )


class _InstrumentedAsyncClient(httpx.AsyncClient):
    _tracer_provider = None
    _request_hook = None
    _response_hook = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._original_transport = self._transport
        self._original_mounts = self._mounts.copy()
        self._is_instrumented_by_opentelemetry = True

        self._transport = AsyncOpenTelemetryTransport(
            self._transport,
            tracer_provider=_InstrumentedAsyncClient._tracer_provider,
            request_hook=_InstrumentedAsyncClient._request_hook,
            response_hook=_InstrumentedAsyncClient._response_hook,
        )

        self._mounts.update(
            {
                url_pattern: (
                    AsyncOpenTelemetryTransport(
                        transport,
                        tracer_provider=_InstrumentedAsyncClient._tracer_provider,
                        request_hook=_InstrumentedAsyncClient._request_hook,
                        response_hook=_InstrumentedAsyncClient._response_hook,
                    )
                    if transport is not None
                    else transport
                )
                for url_pattern, transport in self._original_mounts.items()
            }
        )


class HTTPXClientInstrumentor(BaseInstrumentor):
    # pylint: disable=protected-access,attribute-defined-outside-init
    """An instrumentor for httpx Client and AsyncClient

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> typing.Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments httpx Client and AsyncClient

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
                ``request_hook``: A ``httpx.Client`` hook that receives the span and request
                    that is called right after the span is created
                ``response_hook``: A ``httpx.Client`` hook that receives the span, request,
                    and response that is called right before the span ends
                ``async_request_hook``: Async ``request_hook`` for ``httpx.AsyncClient``
                ``async_response_hook``: Async``response_hook`` for ``httpx.AsyncClient``
        """
        self._original_client = httpx.Client
        self._original_async_client = httpx.AsyncClient
        request_hook = kwargs.get("request_hook")
        response_hook = kwargs.get("response_hook")
        async_request_hook = kwargs.get("async_request_hook")
        async_response_hook = kwargs.get("async_response_hook")
        if callable(request_hook):
            _InstrumentedClient._request_hook = request_hook
        if callable(async_request_hook) and iscoroutinefunction(
            async_request_hook
        ):
            _InstrumentedAsyncClient._request_hook = async_request_hook
        if callable(response_hook):
            _InstrumentedClient._response_hook = response_hook
        if callable(async_response_hook) and iscoroutinefunction(
            async_response_hook
        ):
            _InstrumentedAsyncClient._response_hook = async_response_hook
        tracer_provider = kwargs.get("tracer_provider")
        _InstrumentedClient._tracer_provider = tracer_provider
        _InstrumentedAsyncClient._tracer_provider = tracer_provider
        # Intentionally using a private attribute here, see:
        # https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2538#discussion_r1610603719
        httpx.Client = httpx._api.Client = _InstrumentedClient
        httpx.AsyncClient = _InstrumentedAsyncClient

    def _uninstrument(self, **kwargs):
        httpx.Client = httpx._api.Client = self._original_client
        httpx.AsyncClient = self._original_async_client
        _InstrumentedClient._tracer_provider = None
        _InstrumentedClient._request_hook = None
        _InstrumentedClient._response_hook = None
        _InstrumentedAsyncClient._tracer_provider = None
        _InstrumentedAsyncClient._request_hook = None
        _InstrumentedAsyncClient._response_hook = None

    @staticmethod
    def instrument_client(
        client: typing.Union[httpx.Client, httpx.AsyncClient],
        tracer_provider: TracerProvider = None,
        request_hook: typing.Union[
            typing.Optional[RequestHook], typing.Optional[AsyncRequestHook]
        ] = None,
        response_hook: typing.Union[
            typing.Optional[ResponseHook], typing.Optional[AsyncResponseHook]
        ] = None,
    ) -> None:
        """Instrument httpx Client or AsyncClient

        Args:
            client: The httpx Client or AsyncClient instance
            tracer_provider: A TracerProvider, defaults to global
            request_hook: A hook that receives the span and request that is called
                right after the span is created
            response_hook: A hook that receives the span, request, and response
                that is called right before the span ends
        """
        # pylint: disable=protected-access
        if not hasattr(client, "_is_instrumented_by_opentelemetry"):
            client._is_instrumented_by_opentelemetry = False

        if not client._is_instrumented_by_opentelemetry:
            if isinstance(client, httpx.Client):
                client._original_transport = client._transport
                client._original_mounts = client._mounts.copy()
                transport = client._transport or httpx.HTTPTransport()
                client._transport = SyncOpenTelemetryTransport(
                    transport,
                    tracer_provider=tracer_provider,
                    request_hook=request_hook,
                    response_hook=response_hook,
                )
                client._is_instrumented_by_opentelemetry = True
                client._mounts.update(
                    {
                        url_pattern: (
                            SyncOpenTelemetryTransport(
                                transport,
                                tracer_provider=tracer_provider,
                                request_hook=request_hook,
                                response_hook=response_hook,
                            )
                            if transport is not None
                            else transport
                        )
                        for url_pattern, transport in client._original_mounts.items()
                    }
                )

            if isinstance(client, httpx.AsyncClient):
                transport = client._transport or httpx.AsyncHTTPTransport()
                client._original_mounts = client._mounts.copy()
                client._transport = AsyncOpenTelemetryTransport(
                    transport,
                    tracer_provider=tracer_provider,
                    request_hook=request_hook,
                    response_hook=response_hook,
                )
                client._is_instrumented_by_opentelemetry = True
                client._mounts.update(
                    {
                        url_pattern: (
                            AsyncOpenTelemetryTransport(
                                transport,
                                tracer_provider=tracer_provider,
                                request_hook=request_hook,
                                response_hook=response_hook,
                            )
                            if transport is not None
                            else transport
                        )
                        for url_pattern, transport in client._original_mounts.items()
                    }
                )
        else:
            _logger.warning(
                "Attempting to instrument Httpx client while already instrumented"
            )

    @staticmethod
    def uninstrument_client(
        client: typing.Union[httpx.Client, httpx.AsyncClient]
    ):
        """Disables instrumentation for the given client instance

        Args:
            client: The httpx Client or AsyncClient instance
        """
        if hasattr(client, "_original_transport"):
            client._transport = client._original_transport
            del client._original_transport
            client._is_instrumented_by_opentelemetry = False
        if hasattr(client, "_original_mounts"):
            client._mounts = client._original_mounts.copy()
            del client._original_mounts
        else:
            _logger.warning(
                "Attempting to uninstrument Httpx "
                "client while already uninstrumented"
            )
