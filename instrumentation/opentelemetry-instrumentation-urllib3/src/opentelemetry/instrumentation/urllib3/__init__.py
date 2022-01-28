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
This library allows tracing HTTP requests made by the
`urllib3 <https://urllib3.readthedocs.io/>`_ library.

Usage
-----
.. code-block:: python

    import urllib3
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor

    def strip_query_params(url: str) -> str:
        return url.split("?")[0]

    URLLib3Instrumentor().instrument(
        # Remove all query params from the URL attribute on the span.
        url_filter=strip_query_params,
    )

    http = urllib3.PoolManager()
    response = http.request("GET", "https://www.example.org/")

Configuration
-------------

Request/Response hooks
**********************

The urllib3 instrumentation supports extending tracing behavior with the help of
request and response hooks. These are functions that are called back by the instrumentation
right after a Span is created for a request and right before the span is finished processing a response respectively.
The hooks can be configured as follows:

.. code:: python

    # `request` is an instance of urllib3.connectionpool.HTTPConnectionPool
    def request_hook(span, request):
        pass

    # `request` is an instance of urllib3.connectionpool.HTTPConnectionPool
    # `response` is an instance of urllib3.response.HTTPResponse
    def response_hook(span, request, response):
        pass

    URLLib3Instrumentor.instrument(
        request_hook=request_hook, response_hook=response_hook)
    )

API
---
"""

import contextlib
import typing
from typing import Collection

import urllib3.connectionpool
import wrapt

from opentelemetry import context
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.urllib3.package import _instruments
from opentelemetry.instrumentation.urllib3.version import __version__
from opentelemetry.instrumentation.utils import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    http_status_to_status_code,
    unwrap,
)
from opentelemetry.propagate import inject
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import INVALID_SPAN_CONTEXT, Link, Span, SpanKind, get_current_span, get_tracer
from opentelemetry.trace.status import Status
from opentelemetry.util.http import is_redirect
from opentelemetry.util.http.httplib import set_ip_on_next_http_connection

# A key to a context variable to avoid creating duplicate spans when instrumenting
# both, Session.request and Session.send, since Session.request calls into Session.send
_SUPPRESS_HTTP_INSTRUMENTATION_KEY = context.create_key(
    "suppress_http_instrumentation"
)

_UrlFilterT = typing.Optional[typing.Callable[[str], str]]
_RequestHookT = typing.Optional[
    typing.Callable[
        [
            Span,
            urllib3.connectionpool.HTTPConnectionPool,
            typing.Dict,
            typing.Optional[str],
        ],
        None,
    ]
]
_ResponseHookT = typing.Optional[
    typing.Callable[
        [
            Span,
            urllib3.connectionpool.HTTPConnectionPool,
            urllib3.response.HTTPResponse,
        ],
        None,
    ]
]

_URL_OPEN_ARG_TO_INDEX_MAPPING = {
    "method": 0,
    "url": 1,
}


class URLLib3Instrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments the urllib3 module

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global.
                ``request_hook``: An optional callback that is invoked right after a span is created.
                ``response_hook``: An optional callback which is invoked right before the span is finished processing a response.
                ``url_filter``: A callback to process the requested URL prior
                    to adding it as a span attribute.
        """
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, __version__, tracer_provider)
        _instrument(
            tracer,
            request_hook=kwargs.get("request_hook"),
            response_hook=kwargs.get("response_hook"),
            url_filter=kwargs.get("url_filter"),
        )

    def _uninstrument(self, **kwargs):
        _uninstrument()


def _instrument(
    tracer,
    request_hook: _RequestHookT = None,
    response_hook: _ResponseHookT = None,
    url_filter: _UrlFilterT = None,
):
    def instrumented_urlopen(wrapped, instance, args, kwargs):
        retry = kwargs.get("retries")
        if _is_instrumentation_suppressed(retry and len(retry.history)):
            return wrapped(*args, **kwargs)

        method = _get_url_open_arg("method", args, kwargs).upper()
        url = _get_url(instance, args, kwargs, url_filter)
        headers = _prepare_headers(kwargs)
        body = _get_url_open_arg("body", args, kwargs)

        span_name = f"HTTP {method.strip()}"
        span_attributes = {
            SpanAttributes.HTTP_METHOD: method,
            SpanAttributes.HTTP_URL: url,
        }

        links = None
        # If current call is a retry call
        if retry and len(retry.history):
            # History reflects how many retry attempts have been made
            # Only add retry count on retry scenarios
            if not is_redirect(retry.history[-1].status):
                span_attributes["http.retry_count"] = len(retry.history)
            prev_span_context = get_current_span().get_span_context()
            if prev_span_context is INVALID_SPAN_CONTEXT:
                # If current span is root but we are in a retry scenario, this
                # is a redirect scenario
                prev_span_context = getattr(retry, "_OT_retry_prev_span_context", None)
            if prev_span_context is not INVALID_SPAN_CONTEXT:
                links = (Link(prev_span_context),)

        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes, links=links,
        ) as span, set_ip_on_next_http_connection(span):
            if callable(request_hook):
                request_hook(span, instance, headers, body)
            # If retry call, we must remove headers from kwargs since the underlying call is
            # called with headers already populated in args
            if retry and len(args) >= 4 and args[3] is not None:
                kwargs.pop("headers", None)
            else:
                inject(headers)

            with _suppress_further_instrumentation():
                response = wrapped(*args, **kwargs)
            
            # If redirect scenario, and user enables automatically handle redirects,
            # Store the span context of the original request
            if is_redirect(response.status):
                # response.retries.total will be 0 or False if NOT enabled
                if response.retries and response.retries.total:
                    # We want to store the first response span context that returns a redirect
                    # This is because all subsequent redirect spans should be children
                    # of the original request span
                    if not hasattr(response.retries, "_OT_retry_original_span_context"):
                        response.retries._OT_retry_original_span_context = span.get_span_context()
                    # Update the previous span context in the retry chain
                    response.retries._OT_retry_prev_span_context = span.get_span_context()

            _apply_response(span, response)
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    # Instrument increment in urllib3.util.Retry
    # See https://github.com/urllib3/urllib3/blob/main/src/urllib3/util/retry.py#L421
    # for implementation
    def instrumented_increment(wrapped, instance, args, kwargs):
        original_span_context = getattr(instance, "_OT_retry_original_span_context", None)
        prev_span_context = getattr(instance, "_OT_retry_prev_span_context", None)
        retry = wrapped(*args, **kwargs)
        # Only set original span context to current if not already set
        # In a retry/redirect scenario, we need to keep track of the root span that made
        # the original request
        if not original_span_context:
            original_span_context = get_current_span().get_span_context()
        # We need to keep track of the previous span context because redirect
        # scenario starts a new span tree
        if prev_span_context is None or prev_span_context is INVALID_SPAN_CONTEXT:
            prev_span_context = get_current_span().get_span_context()
        retry._OT_retry_original_span_context = original_span_context
        retry._OT_retry_prev_span_context = prev_span_context
        return retry

    wrapt.wrap_function_wrapper(
        urllib3.connectionpool.HTTPConnectionPool,
        "urlopen",
        instrumented_urlopen,
    )
    wrapt.wrap_function_wrapper(
        urllib3.util.Retry,
        "increment",
        instrumented_increment,
    )


def _get_url_open_arg(name: str, args: typing.List, kwargs: typing.Mapping):
    arg_idx = _URL_OPEN_ARG_TO_INDEX_MAPPING.get(name)
    if arg_idx is not None:
        try:
            return args[arg_idx]
        except IndexError:
            pass
    return kwargs.get(name)


def _get_url(
    instance: urllib3.connectionpool.HTTPConnectionPool,
    args: typing.List,
    kwargs: typing.Mapping,
    url_filter: _UrlFilterT,
) -> str:
    url_or_path = _get_url_open_arg("url", args, kwargs)
    if not url_or_path.startswith("/"):
        url = url_or_path
    else:
        url = instance.scheme + "://" + instance.host
        if _should_append_port(instance.scheme, instance.port):
            url += ":" + str(instance.port)
        url += url_or_path

    if url_filter:
        return url_filter(url)
    return url


def _should_append_port(scheme: str, port: typing.Optional[int]) -> bool:
    if not port:
        return False
    if scheme == "http" and port == 80:
        return False
    if scheme == "https" and port == 443:
        return False
    return True


def _prepare_headers(urlopen_kwargs: typing.Dict) -> typing.Dict:
    headers = urlopen_kwargs.get("headers")

    # avoid modifying original headers on inject
    headers = headers.copy() if headers is not None else {}
    urlopen_kwargs["headers"] = headers

    return headers


def _apply_response(span: Span, response: urllib3.response.HTTPResponse):
    if not span.is_recording():
        return

    span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, response.status)
    span.set_status(Status(http_status_to_status_code(response.status)))


def _is_instrumentation_suppressed(retry: typing.Union[urllib3.util.Retry, bool, int]) -> bool:
    return bool(context.get_value(_SUPPRESS_INSTRUMENTATION_KEY)) or \
        (bool(context.get_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY)) and not \
        retry)


@contextlib.contextmanager
def _suppress_further_instrumentation():
    token = context.attach(
        context.set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
    )
    try:
        yield
    finally:
        context.detach(token)


def _uninstrument():
    unwrap(urllib3.connectionpool.HTTPConnectionPool, "urlopen")
    unwrap(urllib3.util.Retry, "urlopen")
