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

from logging import getLogger
from os import environ
from re import compile as re_compile
from re import search
from time import time

from django.conf import settings

from opentelemetry.context import attach, detach
from opentelemetry.instrumentation.django.version import __version__
from opentelemetry.instrumentation.utils import extract_attributes_from_object
from opentelemetry.instrumentation.wsgi import (
    add_response_attributes,
    carrier_getter,
    collect_request_attributes,
)
from opentelemetry.propagators import extract
from opentelemetry.trace import SpanKind, get_tracer

try:
    from django.core.urlresolvers import (  # pylint: disable=no-name-in-module
        Resolver404,
        resolve,
    )
except ImportError:
    from django.urls import Resolver404, resolve

try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:
    MiddlewareMixin = object

_logger = getLogger(__name__)
_attributes_by_preference = [
    ["http.scheme", "http.host", "http.target"],
    ["http.scheme", "http.server_name", "net.host.port", "http.target"],
    ["http.scheme", "net.host.name", "net.host.port", "http.target"],
    ["http.url"],
]


class _ExcludeList:
    """Class to exclude certain paths (given as a list of regexes) from tracing requests"""

    def __init__(self, excluded_urls):
        self._excluded_urls = excluded_urls
        if self._excluded_urls:
            self._regex = re_compile("|".join(excluded_urls))

    def url_disabled(self, url: str) -> bool:
        return bool(self._excluded_urls and search(self._regex, url))


_root = r"OTEL_PYTHON_{}"


def _get_traced_request_attrs():
    traced_request_attrs = environ.get(
        _root.format("DJANGO_TRACED_REQUEST_ATTRS"), []
    )

    if traced_request_attrs:
        traced_request_attrs = [
            traced_request_attr.strip()
            for traced_request_attr in traced_request_attrs.split(",")
        ]

    return traced_request_attrs


def _get_excluded_urls():
    excluded_urls = environ.get(_root.format("DJANGO_EXCLUDED_URLS"), [])

    if excluded_urls:
        excluded_urls = [
            excluded_url.strip() for excluded_url in excluded_urls.split(",")
        ]

    return _ExcludeList(excluded_urls)


class _DjangoMiddleware(MiddlewareMixin):
    """Django Middleware for OpenTelemetry"""

    _environ_activation_key = (
        "opentelemetry-instrumentor-django.activation_key"
    )
    _environ_token = "opentelemetry-instrumentor-django.token"
    _environ_span_key = "opentelemetry-instrumentor-django.span_key"
    _environ_exception_key = "opentelemetry-instrumentor-django.exception_key"

    _traced_request_attrs = _get_traced_request_attrs()
    _excluded_urls = _get_excluded_urls()

    @staticmethod
    def _get_span_name(request):
        try:
            if getattr(request, "resolver_match"):
                match = request.resolver_match
            else:
                match = resolve(request.path)

            if hasattr(match, "route"):
                return match.route

            # Instead of using `view_name`, better to use `_func_name` as some applications can use similar
            # view names in different modules
            if hasattr(match, "_func_name"):
                return match._func_name  # pylint: disable=protected-access

            # Fallback for safety as `_func_name` private field
            return match.view_name

        except Resolver404:
            return "HTTP {}".format(request.method)

    @staticmethod
    def _get_metric_labels_from_attributes(attributes):
        labels = {}
        labels["http.method"] = attributes.get("http.method", "")
        for attrs in _attributes_by_preference:
            labels_from_attributes = {
                attr: attributes.get(attr, None) for attr in attrs
            }
            if set(attrs).issubset(attributes.keys()):
                labels.update(labels_from_attributes)
                break
        if attributes.get("http.flavor"):
            labels["http.flavor"] = attributes.get("http.flavor")
        return labels

    def process_request(self, request):
        # request.META is a dictionary containing all available HTTP headers
        # Read more about request.META here:
        # https://docs.djangoproject.com/en/3.0/ref/request-response/#django.http.HttpRequest.META

        if self._excluded_urls.url_disabled(request.build_absolute_uri("?")):
            return

        # pylint:disable=W0212
        request._otel_start_time = time()

        request_meta = request.META

        token = attach(extract(carrier_getter, request_meta))

        tracer = get_tracer(__name__, __version__)

        span = tracer.start_span(
            self._get_span_name(request),
            kind=SpanKind.SERVER,
            start_time=request_meta.get(
                "opentelemetry-instrumentor-django.starttime_key"
            ),
        )

        attributes = collect_request_attributes(request_meta)
        # pylint:disable=W0212
        request._otel_labels = self._get_metric_labels_from_attributes(
            attributes
        )

        if span.is_recording():
            attributes = extract_attributes_from_object(
                request, self._traced_request_attrs, attributes
            )
            for key, value in attributes.items():
                span.set_attribute(key, value)

        activation = tracer.use_span(span, end_on_exit=True)
        activation.__enter__()

        request.META[self._environ_activation_key] = activation
        request.META[self._environ_span_key] = span
        request.META[self._environ_token] = token

    # pylint: disable=unused-argument
    def process_view(self, request, view_func, *args, **kwargs):
        # Process view is executed before the view function, here we get the
        # route template from request.resolver_match.  It is not set yet in process_request
        if self._excluded_urls.url_disabled(request.build_absolute_uri("?")):
            return

        if (
            self._environ_activation_key in request.META.keys()
            and self._environ_span_key in request.META.keys()
        ):
            span = request.META[self._environ_span_key]

            if span.is_recording():
                match = getattr(request, "resolver_match")
                if match:
                    route = getattr(match, "route")
                    if route:
                        span.set_attribute("http.route", route)

    def process_exception(self, request, exception):
        if self._excluded_urls.url_disabled(request.build_absolute_uri("?")):
            return

        if self._environ_activation_key in request.META.keys():
            request.META[self._environ_exception_key] = exception

    def process_response(self, request, response):
        if self._excluded_urls.url_disabled(request.build_absolute_uri("?")):
            return response

        if (
            self._environ_activation_key in request.META.keys()
            and self._environ_span_key in request.META.keys()
        ):
            add_response_attributes(
                request.META[self._environ_span_key],
                "{} {}".format(response.status_code, response.reason_phrase),
                response,
            )
            # pylint:disable=W0212
            request._otel_labels["http.status_code"] = str(
                response.status_code
            )
            request.META.pop(self._environ_span_key)

            exception = request.META.pop(self._environ_exception_key, None)
            if exception:
                request.META[self._environ_activation_key].__exit__(
                    type(exception),
                    exception,
                    getattr(exception, "__traceback__", None),
                )
            else:
                request.META[self._environ_activation_key].__exit__(
                    None, None, None
                )
            request.META.pop(self._environ_activation_key)

        if self._environ_token in request.META.keys():
            detach(request.environ.get(self._environ_token))
            request.META.pop(self._environ_token)

        try:
            metric_recorder = getattr(settings, "OTEL_METRIC_RECORDER", None)
            if metric_recorder is not None:
                # pylint:disable=W0212
                metric_recorder.record_server_duration_range(
                    request._otel_start_time, time(), request._otel_labels
                )
        except Exception as ex:  # pylint: disable=W0703
            _logger.warning("Error recording duration metrics: %s", ex)
        return response
