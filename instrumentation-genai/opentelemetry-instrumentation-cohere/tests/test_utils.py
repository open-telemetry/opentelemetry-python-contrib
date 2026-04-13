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

"""Tests for Cohere instrumentation utility functions."""

from types import SimpleNamespace

import pytest

from opentelemetry.instrumentation.cohere.utils import (
    get_server_address_and_port,
    map_finish_reason,
)


class TestMapFinishReason:
    def test_complete(self):
        assert map_finish_reason("COMPLETE") == "stop"

    def test_stop_sequence(self):
        assert map_finish_reason("STOP_SEQUENCE") == "stop"

    def test_max_tokens(self):
        assert map_finish_reason("MAX_TOKENS") == "length"

    def test_tool_call(self):
        assert map_finish_reason("TOOL_CALL") == "tool_calls"

    def test_error(self):
        assert map_finish_reason("ERROR") == "error"

    def test_timeout(self):
        assert map_finish_reason("TIMEOUT") == "error"

    def test_none(self):
        assert map_finish_reason(None) == "error"

    def test_unknown(self):
        assert map_finish_reason("UNKNOWN_REASON") == "unknown_reason"


class TestGetServerAddressAndPort:
    def test_default_address(self):
        client = SimpleNamespace()
        address, port = get_server_address_and_port(client)
        assert address == "api.cohere.com"
        assert port is None

    def test_custom_base_url(self):
        client = SimpleNamespace(base_url="https://custom.cohere.example.com:8443/v2")
        address, port = get_server_address_and_port(client)
        assert address == "custom.cohere.example.com"
        assert port == 8443

    def test_standard_https_port_omitted(self):
        client = SimpleNamespace(base_url="https://api.cohere.com:443/v2")
        address, port = get_server_address_and_port(client)
        assert address == "api.cohere.com"
        assert port is None
