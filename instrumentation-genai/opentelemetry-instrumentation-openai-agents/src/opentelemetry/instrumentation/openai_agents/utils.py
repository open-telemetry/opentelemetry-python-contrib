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

from os import environ
from typing import Optional

OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT"
)
OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS"
)


def is_content_enabled() -> bool:
    """Check if content capture is enabled."""
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT, "false"
    )
    return capture_content.lower() == "true"


def is_metrics_enabled() -> bool:
    """Check if metrics capture is enabled."""
    capture_metrics = environ.get(
        OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS, "true"
    )
    return capture_metrics.lower() == "true"


def get_agent_operation_name(operation: str) -> str:
    """Get the operation name for agent operations."""
    return f"openai_agents.{operation}"


def get_agent_span_name(operation: str, model: Optional[str] = None) -> str:
    """Get the span name for agent operations."""
    if model:
        return f"openai_agents {operation} {model}"
    return f"openai_agents {operation}"
