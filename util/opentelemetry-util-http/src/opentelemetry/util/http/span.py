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
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union
from urllib.parse import urlparse, ParseResult

from opentelemetry.semconv.attributes.network_attributes import NETWORK_PEER_PORT, NETWORK_PEER_ADDRESS

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    _get_schema_url,
    _report_new,
    _report_old,
    _set_http_host_client,
    _set_http_method,
    _set_http_peer_port_client,
    _set_http_url,
    _set_status,
    _StabilityMode,
    set_int_attribute,
    set_string_attribute, _set_http_network_protocol_version,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_STATUS_CODE,
)
from opentelemetry.trace import Span, SpanKind, Tracer, TracerProvider
from opentelemetry.util.http import (
    get_custom_header_attributes,
    normalise_request_header_name,
    normalise_response_header_name,
    sanitize_method, redact_url,
)

HeadersT = Optional[Mapping[str, Union[str, Sequence[str]]]]

_KNOWN_HTTP_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
)


def _get_span_name(method: str) -> str:
    """Generate a span name from an HTTP method.

    Args:
        method: The HTTP method string.

    Returns:
        A sanitized span name based on the HTTP method.
        Returns the uppercase method if known, otherwise "HTTP".
    """
    method: Optional[str] = sanitize_method(method.strip())
    if method == "_OTHER":
        return "HTTP"
    return method


def _normalize_headers(
    headers: HeadersT,
) -> dict[str, list[str]]:
    """Normalize headers to a consistent format for processing.

    Args:
        headers: A mapping of header names to values (string or list of strings).

    Returns:
        A dictionary with header names as keys and lists of values.
    """
    if headers is None:
        return {}

    normalized: dict[str, list[str]] = {}
    for key, value in headers.items():
        if isinstance(value, str):
            normalized[key] = [value]
        elif isinstance(value, (list, tuple, set)):
            normalized[key] = list(value)
    return normalized


def create_http_client_span_attributes(
    method: Optional[str] = None,
    url: Optional[str] = None,
    *,
    status_code: Optional[int] = None,
    request_content_length: Optional[int] = None,
    response_content_length: Optional[int] = None,
    network_protocol_version: Optional[str] = None,
    request_headers: HeadersT = None,
    response_headers: HeadersT = None,
    captured_request_headers: Optional[Sequence[str]] = None,
    captured_response_headers: Optional[Sequence[str]] = None,
    sensitive_headers: Optional[Sequence[str]] = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}

    if method is not None:
        sanitized_method: Optional[str] = sanitize_method(method)
        _set_http_method(
            attributes,
            method,
            sanitized_method,
            sem_conv_opt_in_mode,
        )

    if url is not None:
        redacted_url: str = redact_url(url)
        _set_http_url(attributes, redacted_url, sem_conv_opt_in_mode)

        try:
            parsed_url: ParseResult = urlparse(url)
            if parsed_url.hostname and _report_new(sem_conv_opt_in_mode):
                _set_http_host_client(
                    attributes,
                    parsed_url.hostname,
                    sem_conv_opt_in_mode,
                )
                attributes[NETWORK_PEER_ADDRESS] = parsed_url.hostname

            if parsed_url.port and _report_new(sem_conv_opt_in_mode):
                _set_http_peer_port_client(
                    attributes,
                    parsed_url.port,
                    sem_conv_opt_in_mode,
                )
                attributes[NETWORK_PEER_PORT] = parsed_url.port
        except ValueError:
            pass

    if request_headers is not None and captured_request_headers:
        normalized_request_headers: dict[str, list[str]] = _normalize_headers(request_headers)
        header_attributes: dict[str, Any] = get_custom_header_attributes(
            normalized_request_headers,
            list(captured_request_headers),
            list(sensitive_headers) if sensitive_headers else None,
            normalise_request_header_name,
        )
        attributes.update(header_attributes)

    if status_code is not None:
        status_code_str: str = str(status_code)

        if _report_old(sem_conv_opt_in_mode):
            set_int_attribute(attributes, HTTP_STATUS_CODE, status_code)

        if _report_new(sem_conv_opt_in_mode):
            set_int_attribute(attributes, HTTP_RESPONSE_STATUS_CODE, status_code)

            if status_code >= 400:
                set_string_attribute(attributes, ERROR_TYPE, status_code_str)

    if response_headers is not None and captured_response_headers:
        normalized_response_headers: dict[str, list[str]] = _normalize_headers(response_headers)
        header_attributes: dict[str, Any] = get_custom_header_attributes(
            normalized_response_headers,
            list(captured_response_headers),
            list(sensitive_headers) if sensitive_headers else None,
            normalise_response_header_name,
        )
        attributes.update(header_attributes)

    if network_protocol_version is not None and _report_new(sem_conv_opt_in_mode):
        _set_http_network_protocol_version(
            attributes,
            network_protocol_version,
            sem_conv_opt_in_mode
        )

    return attributes


def create_http_client_span(
    method: str,
    url: str,
    *,
    tracer: Optional[Tracer] = None,
    tracer_provider: Optional[TracerProvider] = None,
    span_name: Optional[str] = None,
    request_headers: HeadersT = None,
    request_content_length: Optional[int] = None,
    network_protocol_version: Optional[str] = None,
    captured_request_headers: Optional[Sequence[str]] = None,
    sensitive_headers: Optional[Sequence[str]] = None,
    attributes: Optional[Mapping[str, Any]] = None,
    start_time: Optional[int] = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> Span:
    if tracer is None:
        tracer = trace.get_tracer(
            instrumenting_module_name=__name__,
            tracer_provider=tracer_provider,
            schema_url=_get_schema_url(sem_conv_opt_in_mode),
        )

    if span_name is None:
        span_name: str = _get_span_name(method)

    span_attributes: dict[str, Any] = create_http_client_span_attributes(
        method=method,
        url=url,
        request_content_length=request_content_length,
        network_protocol_version=network_protocol_version,
        request_headers=request_headers,
        captured_request_headers=captured_request_headers,
        sensitive_headers=sensitive_headers,
        sem_conv_opt_in_mode=sem_conv_opt_in_mode,
    )

    if attributes:
        span_attributes.update(attributes)

    return tracer.start_span(
        name=span_name,
        kind=SpanKind.CLIENT,
        attributes=span_attributes,
        start_time=start_time,
    )


def update_http_client_span(
    span: Span,
    *,
    status_code: Optional[int] = None,
    response_content_length: Optional[int] = None,
    request_content_length: Optional[int] = None,
    network_protocol_version: Optional[str] = None,
    response_headers: HeadersT = None,
    captured_response_headers: Optional[Sequence[str]] = None,
    sensitive_headers: Optional[Sequence[str]] = None,
    custom_attributes: Optional[Mapping[str, Any]] = None,
    sem_conv_opt_in_mode: _StabilityMode = _StabilityMode.DEFAULT,
) -> None:
    if span is None or not span.is_recording():
        return

    if status_code is not None:
        status_code_str: str = str(status_code)

        _set_status(
            span,
            {},
            status_code,
            status_code_str,
            server_span=False,
            sem_conv_opt_in_mode=sem_conv_opt_in_mode,
        )

    additional_attrs: dict[str, Any] = create_http_client_span_attributes(
        response_content_length=response_content_length,
        request_content_length=request_content_length,
        network_protocol_version=network_protocol_version,
        response_headers=response_headers,
        captured_response_headers=captured_response_headers,
        sensitive_headers=sensitive_headers,
        sem_conv_opt_in_mode=sem_conv_opt_in_mode,
    )

    if additional_attrs:
        span.set_attributes(additional_attrs)

    if custom_attributes:
        span.set_attributes(dict(custom_attributes))
