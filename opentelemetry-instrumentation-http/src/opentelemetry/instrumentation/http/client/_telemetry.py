# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from opentelemetry.context import Context, get_current
from opentelemetry.instrumentation.http._internal._body import (
    CONTENT_TYPE_HEADER,
)
from opentelemetry.instrumentation.http._internal._headers import (
    HeaderCapture,
    get_header_value,
)
from opentelemetry.instrumentation.http._internal._http import (
    get_request_size_attributes,
    get_resend_count_attributes,
)
from opentelemetry.instrumentation.http._internal._methods import (
    get_known_methods,
    get_method_attributes,
    get_span_name,
)
from opentelemetry.instrumentation.http._internal._server import (
    get_server_attributes,
)
from opentelemetry.instrumentation.http._internal._suppression import (
    is_http_instrumentation_suppressed,
)
from opentelemetry.instrumentation.http._internal._urls import (
    ExcludedUrls,
    UrlAttributes,
)
from opentelemetry.instrumentation.http._internal._user_agent import (
    get_synthetic_type_attributes,
    get_user_agent,
    get_user_agent_original_attributes,
)
from opentelemetry.instrumentation.http.client._connection import (
    HttpClientConnection,
    HttpClientConnectionInfo,
)
from opentelemetry.instrumentation.http.client._incubating import (
    HttpClientTelemetryDevelopmentOptions,
)
from opentelemetry.instrumentation.http.client._operation import (
    HttpClientOperation,
    _InstrumentedRequest,
)
from opentelemetry.instrumentation.http.client._options import (
    HttpClientTelemetryOptions,
)
from opentelemetry.metrics import MeterProvider
from opentelemetry.propagators.textmap import TextMapPropagator
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_HEADER_TEMPLATE,
    HTTP_RESPONSE_HEADER_TEMPLATE,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanKind,
    TracerProvider,
    get_current_span,
    get_tracer,
    set_span_in_context,
)

_DEFAULT_SCHEMA_URL = Schemas.V1_41_1.value


@dataclass(frozen=True, kw_only=True, slots=True)
class HttpClientRequest:
    """Library agnostic description of an outgoing HTTP request attempt.

    Attributes:
        headers: Request headers. Names must be lowercase, or ``headers`` must
            be a case-insensitive mapping. Values are a single string or a
            sequence of values.
    """

    method: str
    url: str
    headers: Mapping[str, str | Sequence[str]] | None = None
    server_address: str | None = None
    server_port: int | None = None
    url_template: str | None = None
    resend_count: int | None = None
    body_size: int | None = None
    total_size: int | None = None
    user_agent: str | None = None


class HttpClientTelemetry:
    """Records HTTP client telemetry on behalf of HTTP client instrumentations."""

    def __init__(
        self,
        *,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str = _DEFAULT_SCHEMA_URL,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        propagator: TextMapPropagator | None = None,
        options: HttpClientTelemetryOptions | None = None,
        development_options: HttpClientTelemetryDevelopmentOptions | None = None,
    ) -> None:
        """Create HTTP client telemetry.

        Args:
            instrumenting_module_name: Name of the instrumentation library.
            instrumenting_library_version: Version of the instrumentation
                library.
            schema_url: Schema URL of the emitted telemetry. Defaults to the
                latest semantic conventions schema.
            tracer_provider: Tracer provider to use. Defaults to the global
                tracer provider.
            meter_provider: Meter provider to use. Defaults to the global
                meter provider.
            propagator: Propagator used to inject context into outgoing
                requests. Defaults to the global propagator.
            options: Stable options.
            development_options: Development options.

                .. warning::
                    Development options do NOT follow semantic versioning and
                    may have BREAKING changes in any release, including minor
                    and patch releases.
        """
        self._instrumenting_module_name = instrumenting_module_name
        self._schema_url = schema_url
        self._tracer_provider = tracer_provider
        self._meter_provider = meter_provider
        self._propagator = propagator
        self._options = options if options is not None else HttpClientTelemetryOptions()
        self._development_options = (
            development_options if development_options is not None else HttpClientTelemetryDevelopmentOptions()
        )
        self._tracer = get_tracer(
            instrumenting_module_name,
            instrumenting_library_version,
            tracer_provider,
            schema_url=schema_url,
        )
        self._known_methods = (
            None if self._options.capture_all_methods else get_known_methods(self._options.known_methods)
        )
        self._excluded_urls = ExcludedUrls(self._options.excluded_urls)
        self._url_attributes = UrlAttributes(
            sensitive_query_parameters=self._development_options.sensitive_query_parameters,
            capture_url_scheme=bool(self._options.capture_url_scheme),
            capture_url_template=bool(self._development_options.capture_url_template),
        )
        self._capture_network_transport = bool(self._options.capture_network_transport)
        self._capture_user_agent_original = bool(self._options.capture_user_agent_original)
        self._user_agent_synthetic_type_detector = self._development_options.user_agent_synthetic_type_detector
        self._ignore_cancellation_errors = bool(self._development_options.ignore_cancellation_errors)
        self._capture_request_body_size = bool(self._development_options.capture_request_body_size)
        self._capture_request_size = bool(self._development_options.capture_request_size)
        self._capture_response_body_size = bool(self._development_options.capture_response_body_size)
        self._capture_response_size = bool(self._development_options.capture_response_size)
        self._capture_request_body_content = bool(self._development_options.capture_request_body_content)
        self._capture_response_body_content = bool(self._development_options.capture_response_body_content)
        self._body_content_max_size = self._development_options.body_content_max_size
        self._request_headers = HeaderCapture(
            attribute_prefix=HTTP_REQUEST_HEADER_TEMPLATE,
            captured=self._options.captured_request_headers,
            sanitized=self._options.sanitized_headers,
        )
        self._response_headers = HeaderCapture(
            attribute_prefix=HTTP_RESPONSE_HEADER_TEMPLATE,
            captured=self._options.captured_response_headers,
            sanitized=self._options.sanitized_headers,
        )

    def start(
        self,
        request: HttpClientRequest,
        context: Context | None = None,
        *,
        start_time: int | None = None,
    ) -> HttpClientOperation:
        """Start an operation for a request attempt."""
        parent_context = context if context is not None else get_current()
        if is_http_instrumentation_suppressed(parent_context) or self._excluded_urls.is_excluded(request.url):
            span = NonRecordingSpan(get_current_span(parent_context).get_span_context())
            return HttpClientOperation(span, parent_context, self, propagate=False)

        try:
            url_parts: SplitResult | None = urlsplit(request.url)
        except ValueError:
            url_parts = None
        target = request.url_template if self._development_options.capture_url_template else None
        user_agent = (
            get_user_agent(request.user_agent, request.headers)
            if self._capture_user_agent_original or self._user_agent_synthetic_type_detector is not None
            else None
        )
        span = self._tracer.start_span(
            get_span_name(request.method, self._known_methods, target),
            context=parent_context,
            kind=SpanKind.CLIENT,
            attributes=get_method_attributes(request.method, self._known_methods)
            | self._url_attributes.get_attributes(request.url, url_parts, request.url_template)
            | get_server_attributes(url_parts, request.server_address, request.server_port)
            | self._request_headers.get_attributes(request.headers)
            | get_resend_count_attributes(request.resend_count)
            | get_request_size_attributes(
                request.body_size,
                request.total_size,
                capture_body_size=self._capture_request_body_size,
                capture_size=self._capture_request_size,
            )
            | (get_user_agent_original_attributes(user_agent) if self._capture_user_agent_original else {})
            | get_synthetic_type_attributes(user_agent, self._user_agent_synthetic_type_detector),
            start_time=start_time,
        )
        request_content_type = (
            get_header_value(request.headers, CONTENT_TYPE_HEADER) if self._capture_request_body_content else None
        )
        return HttpClientOperation(
            span, set_span_in_context(span, parent_context), self, request_content_type=request_content_type
        )

    def instrument(
        self,
        request: HttpClientRequest,
        context: Context | None = None,
        *,
        start_time: int | None = None,
    ) -> _InstrumentedRequest:
        """Start an operation for a request attempt as a context manager."""
        return _InstrumentedRequest(self.start(request, context, start_time=start_time))

    def start_connection(  # pylint: disable=no-self-use
        self,
        connection: HttpClientConnectionInfo,
        *,
        start_time: int | None = None,
    ) -> HttpClientConnection:
        """Start tracking a connection."""
        return HttpClientConnection()
