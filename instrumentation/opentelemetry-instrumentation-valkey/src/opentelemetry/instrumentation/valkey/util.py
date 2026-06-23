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

_BACKEND_NAME = "valkey"
_DB_SYSTEM = "valkey"

__all__ = [
    "_extract_conn_attributes",
    "_format_command_args",
    "_set_span_attribute_if_value",
    "_value_or_none",
]


def _extract_conn_attributes(
    conn_kwargs: dict[str, Any],
    db_sem_conv_opt_in_mode,
    http_sem_conv_opt_in_mode,
) -> dict[str, Any]:
    """Transform valkey conn info into dict."""
    return _base_extract_conn_attributes(
        conn_kwargs,
        _DB_SYSTEM,
        db_sem_conv_opt_in_mode,
        http_sem_conv_opt_in_mode,
    )
