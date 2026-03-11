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
#
"""
Utility functions for Valkey instrumentation.

These functions delegate to the shared base in
``opentelemetry.instrumentation._redis_valkey.util``, using Valkey-specific
attribute names and conventions.
"""

from __future__ import annotations

from typing import Any

from opentelemetry.instrumentation._redis_valkey.util import (
    _extract_conn_attributes as _base_extract_conn_attributes,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _format_command_args,
    _set_span_attribute_if_value,
    _value_or_none,
)
from opentelemetry.semconv.trace import SpanAttributes

_BACKEND_NAME = "valkey"
_DB_SYSTEM = "valkey"
_DB_SYSTEM_ATTR = SpanAttributes.DB_SYSTEM
_DB_INDEX_ATTR = "db.valkey.database_index"

__all__ = [
    "_extract_conn_attributes",
    "_format_command_args",
    "_set_span_attribute_if_value",
    "_value_or_none",
]


def _extract_conn_attributes(conn_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Transform valkey conn info into dict."""
    return _base_extract_conn_attributes(
        conn_kwargs, _DB_SYSTEM, _DB_SYSTEM_ATTR, _DB_INDEX_ATTR
    )
