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

import os
import threading
from enum import Enum

from opentelemetry.instrumentation.utils import http_status_to_status_code
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode

# TODO: will come through semconv package once updated
_SPAN_ATTRIBUTES_ERROR_TYPE = "error.type"
_SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS = "network.peer.address"
_SPAN_ATTRIBUTES_NETWORK_PEER_PORT = "network.peer.port"
_METRIC_ATTRIBUTES_CLIENT_DURATION_NAME = "http.client.request.duration"
_METRIC_ATTRIBUTES_SERVER_DURATION_NAME = "http.server.request.duration"

_client_duration_attrs_old = [
    SpanAttributes.HTTP_STATUS_CODE,
    SpanAttributes.HTTP_HOST,
    SpanAttributes.NET_PEER_PORT,
    SpanAttributes.NET_PEER_NAME,
    SpanAttributes.HTTP_METHOD,
    SpanAttributes.HTTP_FLAVOR,
    SpanAttributes.HTTP_SCHEME,
]

_client_duration_attrs_new = [
    _SPAN_ATTRIBUTES_ERROR_TYPE,
    SpanAttributes.HTTP_REQUEST_METHOD,
    SpanAttributes.HTTP_RESPONSE_STATUS_CODE,
    SpanAttributes.NETWORK_PROTOCOL_VERSION,
    SpanAttributes.SERVER_ADDRESS,
    SpanAttributes.SERVER_PORT,
    # TODO: Support opt-in for scheme in new semconv
    # SpanAttributes.URL_SCHEME,
]

_server_duration_attrs_old = [
    SpanAttributes.HTTP_METHOD,
    SpanAttributes.HTTP_HOST,
    SpanAttributes.HTTP_SCHEME,
    SpanAttributes.HTTP_STATUS_CODE,
    SpanAttributes.HTTP_FLAVOR,
    SpanAttributes.HTTP_SERVER_NAME,
    SpanAttributes.NET_HOST_NAME,
    SpanAttributes.NET_HOST_PORT,
]

_server_duration_attrs_new = [
    _SPAN_ATTRIBUTES_ERROR_TYPE,
    SpanAttributes.HTTP_REQUEST_METHOD,
    SpanAttributes.HTTP_RESPONSE_STATUS_CODE,
    SpanAttributes.HTTP_ROUTE,
    SpanAttributes.NETWORK_PROTOCOL_VERSION,
    SpanAttributes.URL_SCHEME,
]

_server_active_requests_count_attrs_old = [
    SpanAttributes.HTTP_METHOD,
    SpanAttributes.HTTP_HOST,
    SpanAttributes.HTTP_SCHEME,
    SpanAttributes.HTTP_FLAVOR,
    SpanAttributes.HTTP_SERVER_NAME,
    SpanAttributes.NET_HOST_NAME,
    SpanAttributes.NET_HOST_PORT,
]

_server_active_requests_count_attrs_new = [
    SpanAttributes.HTTP_REQUEST_METHOD,
    SpanAttributes.URL_SCHEME,
]

OTEL_SEMCONV_STABILITY_OPT_IN = "OTEL_SEMCONV_STABILITY_OPT_IN"


class _OpenTelemetryStabilitySignalType:
    HTTP = "http"


class _HTTPStabilityMode(Enum):
    # http - emit the new, stable HTTP and networking conventions ONLY
    HTTP = "http"
    # http/dup - emit both the old and the stable HTTP and networking conventions
    HTTP_DUP = "http/dup"
    # default - continue emitting old experimental HTTP and networking conventions
    DEFAULT = "default"


def _report_new(mode):
    return mode.name != _HTTPStabilityMode.DEFAULT.name


def _report_old(mode):
    return mode.name != _HTTPStabilityMode.HTTP.name


class _OpenTelemetrySemanticConventionStability:
    _initialized = False
    _lock = threading.Lock()
    _OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING = {}

    @classmethod
    def _initialize(cls):
        with _OpenTelemetrySemanticConventionStability._lock:
            if not _OpenTelemetrySemanticConventionStability._initialized:
                # Users can pass in comma delimited string for opt-in options
                # Only values for http stability are supported for now
                opt_in = os.environ.get(OTEL_SEMCONV_STABILITY_OPT_IN, "")
                opt_in_list = []
                if opt_in:
                    opt_in_list = [s.strip() for s in opt_in.split(",")]
                http_opt_in = _HTTPStabilityMode.DEFAULT
                if opt_in_list:
                    # Process http opt-in
                    # http/dup takes priority over http
                    if _HTTPStabilityMode.HTTP_DUP.value in opt_in_list:
                        http_opt_in = _HTTPStabilityMode.HTTP_DUP
                    elif _HTTPStabilityMode.HTTP.value in opt_in_list:
                        http_opt_in = _HTTPStabilityMode.HTTP
                _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING[
                    _OpenTelemetryStabilitySignalType.HTTP
                ] = http_opt_in
                _OpenTelemetrySemanticConventionStability._initialized = True

    @classmethod
    # Get OpenTelemetry opt-in mode based off of signal type (http, messaging, etc.)
    def _get_opentelemetry_stability_opt_in_mode(
        cls,
        signal_type: _OpenTelemetryStabilitySignalType,
    ) -> _HTTPStabilityMode:
        return _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING.get(
            signal_type, _HTTPStabilityMode.DEFAULT
        )


def _filter_semconv_duration_attrs(
    attrs,
    old_attrs,
    new_attrs,
    sem_conv_opt_in_mode=_HTTPStabilityMode.DEFAULT,
):
    filtered_attrs = {}
    # duration is two different metrics depending on sem_conv_opt_in_mode, so no DUP attributes
    allowed_attributes = (
        new_attrs
        if sem_conv_opt_in_mode == _HTTPStabilityMode.HTTP
        else old_attrs
    )
    for key, val in attrs.items():
        if key in allowed_attributes:
            filtered_attrs[key] = val
    return filtered_attrs


def _filter_semconv_active_request_count_attr(
    attrs,
    old_attrs,
    new_attrs,
    sem_conv_opt_in_mode=_HTTPStabilityMode.DEFAULT,
):
    filtered_attrs = {}
    if _report_old(sem_conv_opt_in_mode):
        for key, val in attrs.items():
            if key in old_attrs:
                filtered_attrs[key] = val
    if _report_new(sem_conv_opt_in_mode):
        for key, val in attrs.items():
            if key in new_attrs:
                filtered_attrs[key] = val
    return filtered_attrs


def set_string_attribute(result, key, value):
    if value:
        result[key] = value


def set_int_attribute(result, key, value):
    if value:
        try:
            result[key] = int(value)
        except ValueError:
            return


def _set_http_method(result, original, normalized, sem_conv_opt_in_mode):
    original = original.strip()
    normalized = normalized.strip()
    # See https://github.com/open-telemetry/semantic-conventions/blob/main/docs/http/http-spans.md#common-attributes
    # Method is case sensitive. "http.request.method_original" should not be sanitized or automatically capitalized.
    if original != normalized and _report_new(sem_conv_opt_in_mode):
        set_string_attribute(
            result, SpanAttributes.HTTP_REQUEST_METHOD_ORIGINAL, original
        )

    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_METHOD, normalized)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(
            result, SpanAttributes.HTTP_REQUEST_METHOD, normalized
        )


def _set_http_status_code(result, code, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.HTTP_STATUS_CODE, code)
    if _report_new(sem_conv_opt_in_mode):
        set_int_attribute(
            result, SpanAttributes.HTTP_RESPONSE_STATUS_CODE, code
        )


def _set_http_url(result, url, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_URL, url)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.URL_FULL, url)


def _set_http_scheme(result, scheme, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_SCHEME, scheme)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.URL_SCHEME, scheme)


def _set_http_host(result, host, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_HOST, host)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_ADDRESS, host)


# Client


def _set_http_net_peer_name_client(result, peer_name, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PEER_NAME, peer_name)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_ADDRESS, peer_name)


def _set_http_peer_port_client(result, port, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.NET_PEER_PORT, port)
    if _report_new(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.SERVER_PORT, port)


def _set_http_network_protocol_version(result, version, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_FLAVOR, version)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(
            result, SpanAttributes.NETWORK_PROTOCOL_VERSION, version
        )


# Server


def _set_http_net_host(result, host, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_HOST_NAME, host)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_ADDRESS, host)


def _set_http_net_host_port(result, port, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.NET_HOST_PORT, port)
    if _report_new(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.SERVER_PORT, port)


def _set_http_target(result, target, path, query, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_TARGET, target)
    if _report_new(sem_conv_opt_in_mode):
        if path:
            set_string_attribute(result, SpanAttributes.URL_PATH, path)
        if query:
            set_string_attribute(result, SpanAttributes.URL_QUERY, query)


def _set_http_peer_ip(result, ip, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PEER_IP, ip)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.CLIENT_ADDRESS, ip)


def _set_http_peer_port_server(result, port, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.NET_PEER_PORT, port)
    if _report_new(sem_conv_opt_in_mode):
        set_int_attribute(result, SpanAttributes.CLIENT_PORT, port)


def _set_http_user_agent(result, user_agent, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(
            result, SpanAttributes.HTTP_USER_AGENT, user_agent
        )
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(
            result, SpanAttributes.USER_AGENT_ORIGINAL, user_agent
        )


def _set_http_net_peer_name_server(result, name, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PEER_NAME, name)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.CLIENT_ADDRESS, name)


def _set_http_flavor_version(result, version, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_FLAVOR, version)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(
            result, SpanAttributes.NETWORK_PROTOCOL_VERSION, version
        )


def _set_status(
    span,
    metrics_attributes,
    status_code_str,
    status_code,
    sem_conv_opt_in_mode,
):
    if status_code < 0:
        if _report_new(sem_conv_opt_in_mode):
            span.set_attribute(_SPAN_ATTRIBUTES_ERROR_TYPE, status_code_str)
            metrics_attributes[_SPAN_ATTRIBUTES_ERROR_TYPE] = status_code_str

        span.set_status(
            Status(
                StatusCode.ERROR,
                "Non-integer HTTP status: " + status_code_str,
            )
        )
    else:
        status = http_status_to_status_code(status_code, server_span=True)

        if _report_old(sem_conv_opt_in_mode):
            span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, status_code)
            metrics_attributes[SpanAttributes.HTTP_STATUS_CODE] = status_code
        if _report_new(sem_conv_opt_in_mode):
            span.set_attribute(
                SpanAttributes.HTTP_RESPONSE_STATUS_CODE, status_code
            )
            metrics_attributes[SpanAttributes.HTTP_RESPONSE_STATUS_CODE] = (
                status_code
            )
            if status == StatusCode.ERROR:
                span.set_attribute(
                    _SPAN_ATTRIBUTES_ERROR_TYPE, status_code_str
                )
                metrics_attributes[_SPAN_ATTRIBUTES_ERROR_TYPE] = (
                    status_code_str
                )
        span.set_status(Status(status))


# Get schema version based off of opt-in mode
def _get_schema_url(mode: _HTTPStabilityMode) -> str:
    if mode is _HTTPStabilityMode.DEFAULT:
        return "https://opentelemetry.io/schemas/1.11.0"
    return SpanAttributes.SCHEMA_URL
