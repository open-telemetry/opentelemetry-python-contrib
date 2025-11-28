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

import os
from typing import Any

from opentelemetry.trace import Span


def is_content_enabled() -> bool:
    """Check if message content capture is enabled via environment variable.

    Returns:
        bool: True if OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT is set to 'true'
    """
    return (
        os.getenv(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"
        ).lower()
        == "true"
    )


def set_span_attribute(span: Span, key: str, value: Any) -> None:
    """Set a span attribute if the span is recording and value is not None.

    Args:
        span: The OpenTelemetry span
        key: The attribute key
        value: The attribute value
    """
    if span.is_recording() and value is not None:
        span.set_attribute(key, value)
