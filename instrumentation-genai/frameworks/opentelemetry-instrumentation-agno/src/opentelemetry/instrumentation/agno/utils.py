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

"""Utility functions for Agno instrumentation."""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import Any, Callable, TypeVar

from opentelemetry.trace import Span

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Environment variable for content capture (OTel standard)
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)


def should_capture_content() -> bool:
    """Check if content capture is enabled via environment variable.

    Returns:
        True if content should be captured, False otherwise.
    """
    capture_content = os.environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )
    return capture_content.lower() == "true"


def dont_throw(func: F) -> F:
    """Decorator that catches exceptions and logs them instead of raising.

    Args:
        func: The function to wrap.

    Returns:
        The wrapped function.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.debug(
                "Agno instrumentation failed in %s: %s",
                func.__name__,
                traceback.format_exc(),
            )
            return None

    return wrapper  # type: ignore[return-value]


def set_span_attribute(span: Span, name: str, value: Any) -> None:
    """Safely set a span attribute if the value is not None or empty.

    Args:
        span: The OpenTelemetry span.
        name: The attribute name.
        value: The attribute value.
    """
    if value is not None and value != "":
        span.set_attribute(name, value)


def safe_json_serialize(obj: Any) -> str:
    """Safely serialize an object to JSON string.

    Args:
        obj: The object to serialize.

    Returns:
        JSON string representation, or str(obj) if serialization fails.
    """
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return str(obj)
