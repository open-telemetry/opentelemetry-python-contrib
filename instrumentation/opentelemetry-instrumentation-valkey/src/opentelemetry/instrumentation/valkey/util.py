# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
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
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_REDIS_DATABASE_INDEX,
    DB_SYSTEM,
)

_BACKEND_NAME = "valkey"
_DB_SYSTEM = "valkey"
_DB_SYSTEM_ATTR = DB_SYSTEM
_DB_INDEX_ATTR = DB_REDIS_DATABASE_INDEX

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
