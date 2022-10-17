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

.. code-block:: python

    from opentelemetry.instrumentation.starlite import StarliteInstrumentor
    from starlite import Starlite, MediaType, get

    @get("/foobar", media_type=MediaType.TEXT)
    def home() -> STR:
        return "hi"

    app = Starlite(route_handlers=[home])
    StarliteInstrumentor.instrument_app(app)

Configuration
-------------

Exclude lists
*************
To exclude certain URLs from being tracked, set the environment variable ``OTEL_PYTHON_STARLITE_EXCLUDED_URLS``
(or ``OTEL_PYTHON_EXCLUDED_URLS`` as fallback) with comma delimited regexes representing which URLs to exclude.

For example,

::

    export OTEL_PYTHON_STARLITE_EXCLUDED_URLS="client/.*/info,healthcheck"

will exclude requests such as ``https://site/client/123/info`` and ``https://site/xyz/healthcheck``.

Request/Response hooks
**********************

Utilize request/response hooks to execute custom logic to be performed before/after performing a request. The server request hook takes in a server span and ASGI
scope object for every incoming request. The client request hook is called with the internal span and an ASGI scope which is sent as a dictionary for when the method receive is called.
The client response hook is called with the internal span and an ASGI event which is sent as a dictionary for when the method send is called.

.. code-block:: python

    def server_request_hook(span: Span, scope: dict):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")
    def client_request_hook(span: Span, scope: dict):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_client_request_hook", "some-value")
    def client_response_hook(span: Span, message: dict):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

   StarliteInstrumentor().instrument(server_request_hook=server_request_hook, client_request_hook=client_request_hook, client_response_hook=client_response_hook)

Capture HTTP request and response headers
*****************************************
You can configure the agent to capture predefined HTTP headers as span attributes, according to the `semantic convention <https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/http.md#http-request-and-response-headers>`_.

Request headers
***************
To capture predefined HTTP request headers as span attributes, set the environment variable ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST``
to a comma-separated list of HTTP header names.

For example,

::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST="content-type,custom_request_header"

will extract ``content-type`` and ``custom_request_header`` from request headers and add them as span attributes.

It is recommended that you should give the correct names of the headers to be captured in the environment variable.
Request header names in starlite are case-insensitive. So, giving header name as ``CUStom-Header`` in environment variable will be able capture header with name ``custom-header``.

The name of the added span attribute will follow the format ``http.request.header.<header_name>`` where ``<header_name>`` being the normalized HTTP header name (lowercase, with - characters replaced by _ ).
The value of the attribute will be single item list containing all the header values.

Example of the added span attribute,
``http.request.header.custom_request_header = ["<value1>,<value2>"]``

Response headers
****************
To capture predefined HTTP response headers as span attributes, set the environment variable ``OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE``
to a comma-separated list of HTTP header names.

For example,

::

    export OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE="content-type,custom_response_header"

will extract ``content-type`` and ``custom_response_header`` from response headers and add them as span attributes.

It is recommended that you should give the correct names of the headers to be captured in the environment variable.
Response header names captured in starlite are case insensitive. So, giving header name as ``CUStomHeader`` in environment variable will be able capture header with name ``customheader``.

The name of the added span attribute will follow the format ``http.response.header.<header_name>`` where ``<header_name>`` being the normalized HTTP header name (lowercase, with - characters replaced by _ ).
The value of the attribute will be single item list containing all the header values.

Example of the added span attribute,
``http.response.header.custom_response_header = ["<value1>,<value2>"]``

Note:
    Environment variable names to capture http headers are still experimental, and thus are subject to change.

API
---
"""
import typing
from typing import Collection

from starlite import app as application, PluginProtocol, DefineMiddleware
from starlite.exceptions import NoRouteMatchFoundException
from starlite.types import Scope, Receive, Send

from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.asgi.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.starlite.version import __version__
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Span
from opentelemetry.util.http import get_excluded_urls

_excluded_urls = get_excluded_urls("STARLITE")

_ServerRequestHookT = typing.Optional[typing.Callable[[Span, dict], None]]
_ClientRequestHookT = typing.Optional[typing.Callable[[Span, dict], None]]
_ClientResponseHookT = typing.Optional[typing.Callable[[Span, dict], None]]
_starlite_apps: typing.Set[application.Starlite] = set()


class _InstrumentationMiddleware(OpenTelemetryMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app_is_instrumented = getattr(scope["app"], "_is_instrumented_by_opentelemetry", False)
        if app_is_instrumented:
            await super()(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class _InstrumentationPlugin(PluginProtocol):
    def __init__(self,
                 server_request_hook: _ServerRequestHookT = None,
                 client_request_hook: _ClientRequestHookT = None,
                 client_response_hook: _ClientResponseHookT = None,
                 meter_provider=None,
                 tracer_provider=None,
                 ):
            self.server_request_hook = server_request_hook
            self.client_request_hook = client_request_hook
            self.client_response_hook = client_response_hook
            self.meter_provider = meter_provider
            self.tracer_provider = tracer_provider

    def on_app_init(self, app: application.Starlite) -> None:
        """Instruments a given starlite application"""
        meter = get_meter(__name__, __version__, self.meter_provider)
        if not getattr(app, "_is_instrumented_by_opentelemetry", False):
            app.middleware = [
                DefineMiddleware(
                    _InstrumentationMiddleware,
                    excluded_urls=_excluded_urls,
                    default_span_details=_get_route_details,
                    server_request_hook=self.server_request_hook,
                    client_request_hook=self.client_request_hook,
                    client_response_hook=self.client_response_hook,
                    tracer_provider=self.tracer_provider,
                    meter=meter,
                ),
                *app.middleware
            ]
            setattr(app, "_is_instrumented_by_opentelemetry", True)

            # adding apps to set for uninstrumenting
            if app not in _starlite_apps:
                _starlite_apps.add(app)


class _InstrumentedStarlite(application.Starlite):
    _plugin: _InstrumentationPlugin

    def __init__(self, *args, **kwargs):
        plugins = kwargs.pop("plugins", [])
        kwargs["plugins"] = [self._plugin, *plugins]
        super().__init__(*args, **kwargs)

    def __del__(self):
        _starlite_apps.remove(self)


class StarliteInstrumentor(BaseInstrumentor):
    """An instrumentor for starlite.

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        _InstrumentedStarlite._plugin = _InstrumentationPlugin(
            server_request_hook=kwargs.get("server_request_hook"),
            client_request_hook=kwargs.get("client_request_hook"),
            client_response_hook=kwargs.get("client_response_hook"),
            meter_provider=kwargs.get("_meter_provider"),
            tracer_provider = kwargs.get("tracer_provider"),
        )
        application.Starlite = _InstrumentedStarlite

    def _uninstrument(self, **kwargs):
        """uninstrumenting all created apps by user"""
        for app in _starlite_apps:
            setattr(app, "_is_instrumented_by_opentelemetry", False)

def _get_route_details(scope: Scope):
    """Callback to retrieve the starlite route being served.
    """
    app, route_handler = scope["app"], scope["route_handler"]
    try:
        span_name = app.route_reverse(route_handler.name or str(route_handler))
        attributes = {SpanAttributes.HTTP_ROUTE: span_name} # span_name is a full path in this case.
    except NoRouteMatchFoundException:
        span_name = scope.get("method", "")
        attributes = {}
    return span_name, attributes
