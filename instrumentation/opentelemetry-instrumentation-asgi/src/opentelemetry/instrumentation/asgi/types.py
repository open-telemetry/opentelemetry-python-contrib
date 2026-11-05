# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable
from typing import Any

from opentelemetry.trace import Span

_Scope = dict[str, Any]
_Message = dict[str, Any]

ServerRequestHook = Callable[[Span, _Scope], None] | None
"""
Incoming request callback type.

Args:
    - Server span
    - ASGI scope as a mapping
"""

ClientRequestHook = Callable[[Span, _Scope, _Message], None] | None
"""
Receive callback type.

Args:
    - Internal span
    - ASGI scope as a mapping
    - ASGI event as a mapping
"""

ClientResponseHook = Callable[[Span, _Scope, _Message], None] | None
"""
Send callback type.

Args:
    - Internal span
    - ASGI scope as a mapping
    - ASGI event as a mapping
"""
