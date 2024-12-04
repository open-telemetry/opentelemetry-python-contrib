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
This library allows tracing HTTP Elasticsearch requests made by the
`elasticsearch <https://elasticsearch-py.readthedocs.io/en/master/>`_ library.
"""

import re
from logging import getLogger
from os import environ
from typing import Collection
import elasticsearch
from wrapt import wrap_function_wrapper as _wrap
from opentelemetry.instrumentation.elasticsearch.package import _instruments
from opentelemetry.instrumentation.elasticsearch.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, get_tracer

logger = getLogger(__name__)

_ATTRIBUTES_FROM_RESULT = ["found", "timed_out", "took"]
_DEFAULT_OP_NAME = "request"
_regex_doc_url = re.compile(r"/_doc/([^/]+)")


class ElasticsearchInstrumentor(BaseInstrumentor):
    """An instrumentor for Elasticsearch."""

    def __init__(self, span_name_prefix=None):
        span_name_prefix = span_name_prefix or environ.get(
            "OTEL_PYTHON_ELASTICSEARCH_NAME_PREFIX", "Elasticsearch"
        )
        self._span_name_prefix = span_name_prefix.strip()
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(__name__, __version__, tracer_provider)
        request_hook = kwargs.get("request_hook")
        response_hook = kwargs.get("response_hook")

        _wrap(
            elasticsearch.Transport,
            "perform_request",
            _wrap_perform_request(
                tracer, self._span_name_prefix, request_hook, response_hook
            ),
        )
        _wrap(
            elasticsearch.AsyncTransport,
            "perform_request",
            _wrap_perform_async_request(
                tracer, self._span_name_prefix, request_hook, response_hook
            ),
        )

    def _uninstrument(self, **kwargs):
        unwrap(elasticsearch.Transport, "perform_request")
        unwrap(elasticsearch.AsyncTransport, "perform_request")


def _extract(args, kwargs, span_name_prefix):
    method, url = None, None
    try:
        method, url, *_ = args
    except IndexError:
        logger.warning(
            "Expected perform_request to receive two positional arguments. Got %d",
            len(args),
        )

    op_name = f"{span_name_prefix}{url or method or _DEFAULT_OP_NAME}"
    doc_id = None

    if url:
        match = _regex_doc_url.search(url)
        if match:
            doc_span = match.span()
            op_name = f"{span_name_prefix}{url[:doc_span[0]]}/_doc/:id{url[doc_span[1]:]}"
            doc_id = match.group(1)

    return method, url, op_name, kwargs.get("body"), kwargs.get("params", {}), doc_id


def _set_span_attributes(span, url, method, body, params, doc_id):
    attributes = {SpanAttributes.DB_SYSTEM: "elasticsearch"}
    if url:
        attributes["elasticsearch.url"] = url
    if method:
        attributes["elasticsearch.method"] = method
    if body:
        attributes[SpanAttributes.DB_STATEMENT] = str(body)
    if params:
        attributes["elasticsearch.params"] = str(params)
    if doc_id:
        attributes["elasticsearch.id"] = doc_id

    for key, value in attributes.items():
        span.set_attribute(key, value)


def _set_span_attributes_from_rv(span, return_value):
    for member in _ATTRIBUTES_FROM_RESULT:
        if member in return_value:
            span.set_attribute(f"elasticsearch.{member}", str(return_value[member]))


def _wrap_perform_request(tracer, span_name_prefix, request_hook=None, response_hook=None):
    def wrapper(wrapped, _, args, kwargs):
        method, url, op_name, body, params, doc_id = _extract(args, kwargs, span_name_prefix)

        with tracer.start_as_current_span(op_name, kind=SpanKind.CLIENT) as span:
            if callable(request_hook):
                request_hook(span, method, url, kwargs)

            if span.is_recording():
                _set_span_attributes(span, url, method, body, params, doc_id)

            return_value = wrapped(*args, **kwargs)

            if isinstance(return_value, dict) and span.is_recording():
                _set_span_attributes_from_rv(span, return_value)

            if callable(response_hook):
                response_hook(span, return_value)

            return return_value

    return wrapper


def _wrap_perform_async_request(tracer, span_name_prefix, request_hook=None, response_hook=None):
    async def wrapper(wrapped, _, args, kwargs):
        method, url, op_name, body, params, doc_id = _extract(args, kwargs, span_name_prefix)

        with tracer.start_as_current_span(op_name, kind=SpanKind.CLIENT) as span:
            if callable(request_hook):
                request_hook(span, method, url, kwargs)

            if span.is_recording():
                _set_span_attributes(span, url, method, body, params, doc_id)

            return_value = await wrapped(*args, **kwargs)

            if isinstance(return_value, dict) and span.is_recording():
                _set_span_attributes_from_rv(span, return_value)

            if callable(response_hook):
                response_hook(span, return_value)

            return return_value

    return wrapper