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
Utility functions for Redis instrumentation.

These functions delegate to the shared base in
``opentelemetry.instrumentation._redis_valkey.util``, using Redis-specific
attribute names and conventions.
"""

from __future__ import annotations

from typing import Any

from opentelemetry.instrumentation._redis_valkey.util import (
    _add_create_attributes as _base_add_create_attributes,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _add_search_attributes as _base_add_search_attributes,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _build_span_meta_data_for_pipeline as _base_build_span_meta_data_for_pipeline,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _build_span_name as _base_build_span_name,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _extract_conn_attributes as _base_extract_conn_attributes,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _format_command_args,
    _set_span_attribute_if_value,
    _value_or_none,
)
from opentelemetry.instrumentation._redis_valkey.util import (
    _set_connection_attributes as _base_set_connection_attributes,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_REDIS_DATABASE_INDEX,
    DB_SYSTEM,
)
from opentelemetry.semconv.trace import DbSystemValues
from opentelemetry.trace import Span

_BACKEND_NAME = "redis"
_DB_SYSTEM = DbSystemValues.REDIS.value
_DB_SYSTEM_ATTR = DB_SYSTEM
_DB_INDEX_ATTR = DB_REDIS_DATABASE_INDEX

# Re-export unchanged functions
__all__ = [
    "_extract_conn_attributes",
    "_format_command_args",
    "_set_span_attribute_if_value",
    "_value_or_none",
    "_set_connection_attributes",
    "_build_span_name",
    "_add_create_attributes",
    "_add_search_attributes",
    "_build_span_meta_data_for_pipeline",
]


def _extract_conn_attributes(conn_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Transform redis conn info into dict."""
    return _base_extract_conn_attributes(
        conn_kwargs, _DB_SYSTEM, _DB_SYSTEM_ATTR, _DB_INDEX_ATTR
    )


def _set_connection_attributes(span: Span, conn: Any) -> None:
    _base_set_connection_attributes(
        span, conn, _DB_SYSTEM, _DB_SYSTEM_ATTR, _DB_INDEX_ATTR
    )


def _build_span_name(instance: Any, cmd_args: tuple[Any, ...]) -> str:
    return _base_build_span_name(instance, cmd_args, _BACKEND_NAME)


def _add_create_attributes(span: Span, args: tuple[Any, ...]) -> None:
    _base_add_create_attributes(span, args, _BACKEND_NAME)


def _add_search_attributes(
    span: Span, response: Any, args: tuple[Any, ...]
) -> None:
    _base_add_search_attributes(span, response, args, _BACKEND_NAME)


def _build_span_meta_data_for_pipeline(
    instance: Any,
) -> tuple[list[Any], str, str]:
    return _base_build_span_meta_data_for_pipeline(instance, _BACKEND_NAME)
