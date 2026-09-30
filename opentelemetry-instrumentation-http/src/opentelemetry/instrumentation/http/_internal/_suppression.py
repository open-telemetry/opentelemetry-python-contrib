# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.context import Context, get_value

# The suppression keys are private to the API and may be moved or removed, in
# which case the corresponding check is skipped.
try:
    from opentelemetry.context import _SUPPRESS_INSTRUMENTATION_KEY
except ImportError:
    _SUPPRESS_INSTRUMENTATION_KEY = None

try:
    from opentelemetry.context import _SUPPRESS_HTTP_INSTRUMENTATION_KEY
except ImportError:
    _SUPPRESS_HTTP_INSTRUMENTATION_KEY = None


def is_http_instrumentation_suppressed(context: Context) -> bool:
    """Return whether instrumentation or HTTP instrumentation is suppressed in ``context``."""
    return any(
        key is not None and bool(get_value(key, context))
        for key in (_SUPPRESS_INSTRUMENTATION_KEY, _SUPPRESS_HTTP_INSTRUMENTATION_KEY)
    )
