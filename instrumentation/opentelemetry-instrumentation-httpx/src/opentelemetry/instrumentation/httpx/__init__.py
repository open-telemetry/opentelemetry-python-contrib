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

import typing

import httpcore
import httpx
import wrapt

from opentelemetry import context
from opentelemetry.instrumentation.httpx.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    http_status_to_status_code,
    unwrap,
)
from opentelemetry.propagate import inject
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer, TracerProvider, get_tracer
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import Status

URL = typing.Tuple[bytes, bytes, typing.Optional[int], bytes]
Headers = typing.List[typing.Tuple[bytes, bytes]]
RequestHook = typing.Callable[[Span, httpx.Request], None]
ResponseHook = typing.Callable[[Span, httpx.Request, httpx.Response], None]


def _get_default_span_name(method: str) -> str:
    return "HTTP {}".format(method).strip()


def _apply_status_code(span: Span, status_code: int) -> None:
    if not span.is_recording():
        return

    span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, status_code)
    span.set_status(Status(http_status_to_status_code(status_code)))


def _prepare_attributes(method: bytes, url: URL) -> typing.Dict[str, str]:
    _method = method.decode().upper()
    _url = str(httpx.URL(url))
    span_attributes = {
        SpanAttributes.HTTP_METHOD: _method,
        SpanAttributes.HTTP_URL: _url,
    }
    return span_attributes


def _prepare_headers(headers: typing.Optional[Headers]) -> httpx.Headers:
    return httpx.Headers(headers)


class SyncOpenTelemetryTransport(httpcore.SyncHTTPTransport):
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
        transport: httpcore.SyncHTTPTransport,
        tracer_provider: typing.Optional[TracerProvider] = None,
        request_hook: typing.Optional[RequestHook] = None,
        response_hook: typing.Optional[ResponseHook] = None,
    ):
        self._transport = transport
        self._tracer = get_tracer(
            __name__,
            instrumenting_library_version=__version__,
            tracer_provider=tracer_provider,
        )
        self._request_hook = request_hook
        self._response_hook = response_hook

    def request(
        self,
        method: bytes,
        url: URL,
        headers: typing.Optional[Headers] = None,
        stream: typing.Optional[httpcore.SyncByteStream] = None,
        ext: typing.Optional[dict] = None,
    ) -> typing.Tuple[int, "Headers", httpcore.SyncByteStream, dict]:
        """Add request info to span."""
        if context.get_value("suppress_instrumentation"):
            return self._transport.request(
                method, url, headers=headers, stream=stream, ext=ext
            )

        span_attributes = _prepare_attributes(method, url)
        _headers = _prepare_headers(headers)
        span_name = _get_default_span_name(span_attributes[SpanAttributes.HTTP_METHOD])
        request = httpx.Request(
            method,
            url,
            headers=headers,
            stream=stream,
        )

        with self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            if self._request_hook is not None:
                self._request_hook(span, request)

            inject(_headers)

            status_code, headers, stream, extensions = self._transport.request(
                method, url, headers=_headers.raw, stream=stream, ext=ext
            )

            _apply_status_code(span, status_code)

            if self._response_hook is not None:
                response = httpx.Response(status_code=status_code, headers=headers, stream=stream, ext=extensions, request=request)
                response.read()
                self._response_hook(span, request, response)

        return status_code, headers, stream, extensions


class AsyncOpenTelemetryTransport(httpcore.AsyncHTTPTransport):
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
        transport: httpcore.AsyncHTTPTransport,
        tracer_provider: typing.Optional[TracerProvider] = None,
        request_hook: typing.Optional[RequestHook] = None,
        response_hook: typing.Optional[ResponseHook] = None,
    ):
        self._transport = transport
        self._tracer = get_tracer(
            __name__,
            instrumenting_library_version=__version__,
            tracer_provider=tracer_provider,
        )
        self._request_hook = request_hook
        self._response_hook = response_hook

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: typing.Optional[Headers] = None,
        stream: typing.Optional[httpcore.AsyncByteStream] = None,
        ext: typing.Optional[dict] = None,
    ) -> typing.Tuple[int, "Headers", httpcore.AsyncByteStream, dict]:
        """Add request info to span."""
        if context.get_value("suppress_instrumentation"):
            return await self._transport.arequest(
                method, url, headers=headers, stream=stream, ext=ext
            )

        span_attributes = _prepare_attributes(method, url)
        _headers = _prepare_headers(headers)
        span_name = _get_default_span_name(span_attributes[SpanAttributes.HTTP_METHOD])
        request = httpx.Request(
            method,
            url,
            headers=headers,
            stream=stream,
        )

        with self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            if self._request_hook is not None:
                self._request_hook(span, request)

            inject(_headers)

            (
                status_code,
                headers,
                stream,
                extensions,
            ) = await self._transport.arequest(
                method, url, headers=_headers.raw, stream=stream, ext=ext
            )

            _apply_status_code(span, status_code)

            if self._response_hook is not None:
                response = httpx.Response(status_code=status_code, headers=headers, stream=stream, ext=extensions, request=request)
                response.read()
                self._response_hook(span, request, response)

        return status_code, headers, stream, extensions


def _instrument(
    tracer_provider: TracerProvider = None,
    request_hook: typing.Optional[RequestHook] = None,
    response_hook: typing.Optional[ResponseHook] = None,
) -> None:
    """Enables tracing of all Client and AsyncClient instances

    When a Client or AsyncClient gets created, a telemetry transport is passed
    in to the instance.
    """
    # pylint:disable=unused-argument
    def instrumented_sync_init(wrapped, instance, args, kwargs):
        if context.get_value("suppress_instrumentation"):
            return wrapped(*args, **kwargs)

        transport = kwargs.get("transport") or httpx.HTTPTransport()
        telemetry_transport = SyncOpenTelemetryTransport(
            transport,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )

        kwargs["transport"] = telemetry_transport
        return wrapped(*args, **kwargs)

    def instrumented_async_init(wrapped, instance, args, kwargs):
        if context.get_value("suppress_instrumentation"):
            return wrapped(*args, **kwargs)

        transport = kwargs.get("transport") or httpx.AsyncHTTPTransport()
        telemetry_transport = AsyncOpenTelemetryTransport(
            transport,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )

        kwargs["transport"] = telemetry_transport
        return wrapped(*args, **kwargs)

    wrapt.wrap_function_wrapper(
        httpx.Client, "__init__", instrumented_sync_init
    )

    wrapt.wrap_function_wrapper(
        httpx.AsyncClient, "__init__", instrumented_async_init
    )


def _instrument_client(
    client: typing.Union[httpx.Client, httpx.AsyncClient],
    tracer_provider: TracerProvider = None,
    request_hook: typing.Optional[RequestHook] = None,
    response_hook: typing.Optional[ResponseHook] = None,
) -> None:
    """Enables instrumentation for the given Client or AsyncClient"""
    # pylint: disable=protected-access
    if isinstance(client, httpx.Client):
        transport = client._transport or httpcore.SyncHTTPTransport()
        telemetry_transport = SyncOpenTelemetryTransport(
            transport,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )
    elif isinstance(client, httpx.AsyncClient):
        transport = client._transport or httpcore.AsyncHTTPTransport()
        telemetry_transport = AsyncOpenTelemetryTransport(
            transport,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )
    else:
        raise TypeError("Invalid client provided")
    client._transport = telemetry_transport


def _uninstrument() -> None:
    """Disables instrumenting for all newly created Client and AsyncClient instances"""
    unwrap(httpx.Client, "__init__")
    unwrap(httpx.AsyncClient, "__init__")


def _uninstrument_client(
    client: typing.Union[httpx.Client, httpx.AsyncClient]
) -> None:
    """Disables instrumentation for the given Client or AsyncClient"""
    # pylint: disable=protected-access
    telemetry_transport: typing.Union[
        SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport
    ] = client._transport
    client._transport = telemetry_transport._transport


class HTTPXClientInstrumentor(BaseInstrumentor):
    """An instrumentor for httpx Client and AsyncClient

    See `BaseInstrumentor`
    """

    def _instrument(self, **kwargs):
        """Instruments httpx Client and AsyncClient

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
                ``request_hook``: A hook that receives the span and request that is called
                    right after the span is created
                ``response_hook``: A hook that receives the span, request, and response
                    that is called right before the span ends
        """
        _instrument(
            tracer_provider=kwargs.get("tracer_provider"),
            request_hook=kwargs.get("request_hook"),
            response_hook=kwargs.get("response_hook"),
        )

    def _uninstrument(self, **kwargs):
        _uninstrument()

    @staticmethod
    def instrument_client(
        client: typing.Union[httpx.Client, httpx.AsyncClient],
        tracer_provider: TracerProvider = None,
        request_hook: typing.Optional[RequestHook] = None,
        response_hook: typing.Optional[ResponseHook] = None,
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
        _instrument_client(
            client,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )

    @staticmethod
    def uninstrument_client(
        client: typing.Union[httpx.Client, httpx.AsyncClient]
    ):
        """Disables instrumentation for the given client instance

        Args:
            client: The httpx Client or AsyncClient instance
        """
        _uninstrument_client(client)
