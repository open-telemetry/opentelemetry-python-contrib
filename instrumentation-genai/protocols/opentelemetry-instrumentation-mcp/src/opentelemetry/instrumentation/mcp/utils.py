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

from __future__ import annotations

import functools
import json
import logging
import traceback
from os import environ
from typing import Any, Callable, Optional, TypeVar

from opentelemetry.trace import Span

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)


class Config:
    """Configuration for the MCP instrumentation."""

    exception_logger: Optional[Callable[[Exception], None]] = None


def is_content_enabled() -> bool:
    """Check if content capture is enabled via environment variable."""
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )
    return capture_content.lower() == "true"


def dont_throw(func: F) -> F:
    """Decorator that prevents exceptions from propagating.

    This ensures that instrumentation errors don't affect the application.
    """
    func_logger = logging.getLogger(func.__module__)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            func_logger.debug(
                "Instrumentation failed in %s, error: %s",
                func.__name__,
                traceback.format_exc(),
            )
            if Config.exception_logger:
                Config.exception_logger(e)

    return wrapper  # type: ignore[return-value]


def set_span_attribute(span: Span, name: str, value: Any) -> None:
    """Set a span attribute if the value is not None or empty."""
    if value is not None and value != "":
        span.set_attribute(name, value)


def safe_json_dumps(obj: Any) -> Optional[str]:
    """Safely serialize object to JSON."""
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return None
