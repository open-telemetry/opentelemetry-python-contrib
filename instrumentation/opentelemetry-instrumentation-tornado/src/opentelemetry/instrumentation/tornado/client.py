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

import functools
from time import time_ns

from tornado.httpclient import HTTPError, HTTPRequest

from opentelemetry import trace
from opentelemetry.instrumentation.utils import http_status_to_status_code
from opentelemetry.propagate import inject
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_STATUS_CODE,
    HTTP_URL,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.http import redact_url


def _normalize_request(args, kwargs):
    req = args[0]
    if not isinstance(req, str):
        return (args, kwargs)

    new_kwargs = {}
    for param in ("callback", "raise_error"):
        if param in kwargs:
            new_kwargs[param] = kwargs.pop(param)

    req = HTTPRequest(req, **kwargs)
    new_args = [req]
    new_args.extend(args[1:])
    return (new_args, new_kwargs)


def fetch_async(
    tracer,
    request_hook,
    response_hook,
    duration_histogram,
    request_size_histogram,
    response_size_histogram,
    func,
    _,
    args,
    kwargs,
):
    start_time = time_ns()

    # Return immediately if no args were provided (error)
    # or original_request is set (meaning we are in a redirect step).
    if len(args) == 0 or hasattr(args[0], "original_request"):
        return func(*args, **kwargs)

    # Force the creation of a HTTPRequest object if needed,
    # so we can inject the context into the headers.
    args, kwargs = _normalize_request(args, kwargs)
    request = args[0]

    span = tracer.start_span(
        request.method,
        kind=trace.SpanKind.CLIENT,
        start_time=start_time,
    )
    if request_hook:
        request_hook(span, request)

    if span.is_recording():
        attributes = {
            HTTP_URL: redact_url(request.url),
            HTTP_METHOD: request.method,
        }
        for key, value in attributes.items():
            span.set_attribute(key, value)

    with trace.use_span(span):
        inject(request.headers)
        future = func(*args, **kwargs)
        future.add_done_callback(
            functools.partial(
                _finish_tracing_callback,
                span=span,
                response_hook=response_hook,
                duration_histogram=duration_histogram,
                request_size_histogram=request_size_histogram,
                response_size_histogram=response_size_histogram,
            )
        )
        return future


def _finish_tracing_callback(
    future,
    span,
    response_hook,
    duration_histogram,
    request_size_histogram,
    response_size_histogram,
):
    response = None
    status_code = None
    status = None
    description = None

    exc = future.exception()
    if exc:
        description = f"{type(exc).__qualname__}: {exc}"
        if isinstance(exc, HTTPError):
            response = exc.response
            status_code = exc.code
            status = Status(
                status_code=http_status_to_status_code(status_code),
                description=description,
            )
        else:
            status = Status(
                status_code=StatusCode.ERROR,
                description=description,
            )
            span.record_exception(exc)
    else:
        response = future.result()
        status_code = response.code
        status = Status(
            status_code=http_status_to_status_code(status_code),
            description=description,
        )

    if status_code is not None:
        span.set_attribute(HTTP_STATUS_CODE, status_code)
    span.set_status(status)

    if response is not None:
        metric_attributes = _create_metric_attributes(response)
        request_size = int(response.request.headers.get("Content-Length", 0))
        response_size = int(response.headers.get("Content-Length", 0))

        duration_histogram.record(
            response.request_time, attributes=metric_attributes
        )
        request_size_histogram.record(
            request_size, attributes=metric_attributes
        )
        response_size_histogram.record(
            response_size, attributes=metric_attributes
        )

    if response_hook:
        response_hook(span, future)
    span.end()


def _create_metric_attributes(response):
    metric_attributes = {
        HTTP_STATUS_CODE: response.code,
        HTTP_URL: redact_url(response.request.url),
        HTTP_METHOD: response.request.method,
    }

    return metric_attributes
