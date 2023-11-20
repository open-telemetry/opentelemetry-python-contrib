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
from re import escape, sub
from typing import Dict, Optional, Sequence



from opentelemetry.semconv.trace import SpanAttributes


def set_string_attribute(dict, key, value):
    if value:
        dict[key] = value


def set_int_attribute(dict, key, value):
    if value:
        try:
            dict[key] = int(value)
        except ValueError:
            return


def _set_http_method(result, original, normalized, sem_conv_opt_in_mode):
    original = original.strip()
    normalized = normalized.strip()
    # See https://github.com/open-telemetry/semantic-conventions/blob/main/docs/http/http-spans.md#common-attributes
    # Method is case sensitive. "http.request.method_original" should not be sanitized or automatically capitalized.
    if original != normalized and sem_conv_opt_in_mode != _OpenTelemetryStabilityMode.DEFAULT:
        set_string_attribute(result, SpanAttributes.HTTP_REQUEST_METHOD_ORIGINAL, original)

    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_METHOD, normalized)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_REQUEST_METHOD, normalized)


def _set_http_url(result, url, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_URL, url)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.URL_FULL, url)


def _set_http_scheme(result, scheme, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_SCHEME, scheme)
    # TODO: Support opt-in for scheme in new semconv
    # if _report_new(sem_conv_opt_in_mode):
    #     set_string_attribute(result, SpanAttributes.URL_SCHEME, scheme)


def _set_http_hostname(result, hostname, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_HOST, hostname)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_ADDRESS, hostname)


def _set_http_net_peer_name(result, peer_name, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PEER_NAME, peer_name)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_ADDRESS, peer_name)


def _set_http_port(result, port, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PEER_PORT, port)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.SERVER_PORT, port)


def _set_http_status_code(result, code, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_STATUS_CODE, code)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_RESPONSE_STATUS_CODE, code)


def _set_http_network_protocol_version(result, version, sem_conv_opt_in_mode):
    if _report_old(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.HTTP_FLAVOR, version)
    if _report_new(sem_conv_opt_in_mode):
        set_string_attribute(result, SpanAttributes.NET_PROTOCOL_VERSION, version)



_OTEL_SEMCONV_STABILITY_OPT_IN_KEY = "OTEL_SEMCONV_STABILITY_OPT_IN"

# Old to new http semantic convention mappings
_OTEL_HTTP_SEMCONV_MIGRATION_MAPPING = {
    SpanAttributes.HTTP_METHOD: SpanAttributes.HTTP_REQUEST_METHOD,
    SpanAttributes.HTTP_STATUS_CODE: SpanAttributes.HTTP_RESPONSE_STATUS_CODE,
    SpanAttributes.HTTP_SCHEME: SpanAttributes.URL_SCHEME,
    SpanAttributes.HTTP_URL: SpanAttributes.URL_FULL,
    SpanAttributes.HTTP_REQUEST_CONTENT_LENGTH: SpanAttributes.HTTP_REQUEST_BODY_SIZE,
    SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH: SpanAttributes.HTTP_RESPONSE_BODY_SIZE,
    SpanAttributes.NET_HOST_NAME: SpanAttributes.SERVER_ADDRESS,
    SpanAttributes.NET_HOST_PORT: SpanAttributes.SERVER_PORT,
    SpanAttributes.NET_SOCK_HOST_ADDR: SpanAttributes.SERVER_SOCKET_ADDRESS,
    SpanAttributes.NET_SOCK_HOST_PORT: SpanAttributes.SERVER_SOCKET_PORT,
    SpanAttributes.NET_TRANSPORT: SpanAttributes.NETWORK_TRANSPORT,
    SpanAttributes.NET_PROTOCOL_NAME: SpanAttributes.NETWORK_PROTOCOL_NAME,
    SpanAttributes.NET_PROTOCOL_VERSION: SpanAttributes.NETWORK_PROTOCOL_VERSION,
    SpanAttributes.NET_SOCK_FAMILY: SpanAttributes.NETWORK_TYPE,
    SpanAttributes.NET_PEER_IP: SpanAttributes.CLIENT_SOCKET_ADDRESS,
    SpanAttributes.NET_HOST_IP: SpanAttributes.SERVER_SOCKET_ADDRESS,
    SpanAttributes.HTTP_SERVER_NAME: SpanAttributes.SERVER_ADDRESS,
    SpanAttributes.HTTP_RETRY_COUNT: SpanAttributes.HTTP_RESEND_COUNT,
    SpanAttributes.HTTP_REQUEST_CONTENT_LENGTH_UNCOMPRESSED: SpanAttributes.HTTP_REQUEST_BODY_SIZE,
    SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH_UNCOMPRESSED: SpanAttributes.HTTP_RESPONSE_BODY_SIZE,
    SpanAttributes.HTTP_USER_AGENT: SpanAttributes.USER_AGENT_ORIGINAL,
    SpanAttributes.NET_APP_PROTOCOL_NAME: SpanAttributes.NETWORK_PROTOCOL_NAME,
    SpanAttributes.NET_APP_PROTOCOL_VERSION: SpanAttributes.NETWORK_PROTOCOL_VERSION,
    SpanAttributes.HTTP_CLIENT_IP: SpanAttributes.CLIENT_ADDRESS,
    SpanAttributes.HTTP_FLAVOR: SpanAttributes.NETWORK_PROTOCOL_VERSION,
    SpanAttributes.NET_HOST_CONNECTION_TYPE: SpanAttributes.NETWORK_CONNECTION_TYPE,
    SpanAttributes.NET_HOST_CONNECTION_SUBTYPE: SpanAttributes.NETWORK_CONNECTION_SUBTYPE,
    SpanAttributes.NET_HOST_CARRIER_NAME: SpanAttributes.NETWORK_CARRIER_NAME,
    SpanAttributes.NET_HOST_CARRIER_MCC: SpanAttributes.NETWORK_CARRIER_MCC,
    SpanAttributes.NET_HOST_CARRIER_MNC: SpanAttributes.NETWORK_CARRIER_MNC,
}

# Special mappings handled case-by-case
_OTEL_HTTP_SEMCONV_MIGRATION_MAPPING_SPECIAL = {
    SpanAttributes.HTTP_TARGET: (SpanAttributes.URL_PATH, SpanAttributes.URL_QUERY),
    SpanAttributes.HTTP_HOST: (SpanAttributes.SERVER_ADDRESS, SpanAttributes.SERVER_PORT),
}


class _OpenTelemetryStabilitySignalType:
    HTTP = "http"


class _OpenTelemetryStabilityMode(Enum):
    # http - emit the new, stable HTTP and networking conventions ONLY
    HTTP = "http"
    # http/dup - emit both the old and the stable HTTP and networking conventions
    HTTP_DUP = "http/dup"
    # default - continue emitting old experimental HTTP and networking conventions
    DEFAULT = "default"


def _report_new(mode):
    return mode.name != _OpenTelemetryStabilityMode.DEFAULT.name

def _report_old(mode):
    return mode.name != _OpenTelemetryStabilityMode.HTTP.name


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
                opt_in = os.environ.get(_OTEL_SEMCONV_STABILITY_OPT_IN_KEY, "")
                opt_in_list = []
                if opt_in:
                    opt_in_list = [s.strip() for s in opt_in.split(",")]
                http_opt_in = _OpenTelemetryStabilityMode.DEFAULT
                if opt_in_list:
                    # Process http opt-in
                    # http/dup takes priority over http
                    if (
                        _OpenTelemetryStabilityMode.HTTP_DUP.value
                        in opt_in_list
                    ):
                        http_opt_in = _OpenTelemetryStabilityMode.HTTP_DUP
                    elif _OpenTelemetryStabilityMode.HTTP.value in opt_in_list:
                        http_opt_in = _OpenTelemetryStabilityMode.HTTP
                _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING[
                    _OpenTelemetryStabilitySignalType.HTTP
                ] = http_opt_in
                _OpenTelemetrySemanticConventionStability._initialized = True


    @classmethod
    # Get OpenTelemetry opt-in mode based off of signal type (http, messaging, etc.)
    def _get_opentelemetry_stability_opt_in_mode(
        cls,
        signal_type: _OpenTelemetryStabilitySignalType,
    ) -> _OpenTelemetryStabilityMode:
        return _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING.get(
            signal_type, _OpenTelemetryStabilityMode.DEFAULT
        )


# Get new semantic convention attribute key based off old attribute key
# If no new attribute key exists for old attribute key, returns old attribute key
def _get_new_convention(old: str) -> str:
    return _OTEL_HTTP_SEMCONV_MIGRATION_MAPPING.get(old, old)


# Get updated attributes based off of opt-in mode and client/server
def _get_attributes_based_on_stability_mode(
    mode: _OpenTelemetryStabilityMode,
    old_attributes: Dict[str, str],
) -> Dict[str, str]:
    if mode is _OpenTelemetryStabilityMode.DEFAULT:
        return old_attributes
    attributes = {}
    for old_key, value in old_attributes.items():
        new_key = _get_new_convention(old_key)
        attributes[new_key] = value
        if mode is _OpenTelemetryStabilityMode.HTTP_DUP:
            attributes[old_key] = value
        
    return attributes
