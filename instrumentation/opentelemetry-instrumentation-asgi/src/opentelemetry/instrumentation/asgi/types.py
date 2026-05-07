# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Callable, Dict, Optional

from opentelemetry.trace import Span

_Scope = Dict[str, Any]
_Message = Dict[str, Any]

ServerRequestHook = Optional[Callable[[Span, _Scope], None]]
"""
Incoming request callback type.

Args:
    - Server span
    - ASGI scope as a mapping
"""

ClientRequestHook = Optional[Callable[[Span, _Scope, _Message], None]]
"""
Receive callback type.

Args:
    - Internal span
    - ASGI scope as a mapping
    - ASGI event as a mapping
"""

ClientResponseHook = Optional[Callable[[Span, _Scope, _Message], None]]
"""
Send callback type.

Args:
    - Internal span
    - ASGI scope as a mapping
    - ASGI event as a mapping
"""
