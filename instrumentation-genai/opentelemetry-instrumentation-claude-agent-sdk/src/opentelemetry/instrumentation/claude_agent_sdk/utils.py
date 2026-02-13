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

"""Utility functions for Claude Agent SDK instrumentation."""

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GenAiProviderNameValues,
)
from opentelemetry.util.genai.types import Text, ToolCall

logger = logging.getLogger(__name__)


def get_model_from_options_or_env(options: Any) -> str:
    """
    Get model name from options or environment variables.
    """
    model = "unknown"

    if options:
        model = getattr(options, "model", None)

        # Key: If options.model is None, read from environment variables
        # This mimics Claude CLI behavior: when no --model parameter, CLI reads environment variables
        if not model:
            model = (
                os.getenv("ANTHROPIC_MODEL")
                or os.getenv("ANTHROPIC_SMALL_FAST_MODEL")
                or "unknown"
            )

    return model


def infer_provider_from_base_url(base_url: Optional[str] = None) -> str:
    """
    Infer the provider name from ANTHROPIC_BASE_URL environment variable.

    Only recognizes known providers from OpenTelemetry semantic conventions.
    Returns "anthropic" for unknown providers as these are typically Anthropic-compatible API services.

    Args:
        base_url: Optional base URL to check. If not provided, reads from ANTHROPIC_BASE_URL env var.

    """
    if base_url is None:
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "")

    if not base_url:
        return GenAiProviderNameValues.ANTHROPIC.value

    try:
        parsed = urlparse(base_url)
        hostname = parsed.hostname or ""

        # Check for known providers (order matters: most specific first)
        if "dashscope" in hostname or "aliyuncs.com" in hostname:
            return "dashscope"

        if "moonshot" in hostname:
            return "moonshot"

        return GenAiProviderNameValues.ANTHROPIC.value

    except Exception:
        return GenAiProviderNameValues.ANTHROPIC.value


def extract_message_parts(message: Any) -> List[Any]:
    """
    Extract parts (text + tool calls) from an AssistantMessage.

    Args:
        message: AssistantMessage object

    Returns:
        List of message parts (Text, ToolCall)
    """
    parts = []
    if not hasattr(message, "content"):
        return parts

    for block in message.content:
        block_type = type(block).__name__
        if block_type == "TextBlock":
            parts.append(Text(content=getattr(block, "text", "")))
        elif block_type == "ToolUseBlock":
            tool_call = ToolCall(
                id=getattr(block, "id", ""),
                name=getattr(block, "name", ""),
                arguments=getattr(block, "input", {}),
            )
            parts.append(tool_call)

    return parts


def extract_usage_metadata(usage: Any) -> Dict[str, Any]:
    """
    Extract and normalize usage metrics from a Claude usage object or dict.

    Only extracts standard OpenTelemetry fields: input_tokens and output_tokens.
    Cache tokens are extracted temporarily for summing into input_tokens.

    Args:
        usage: Usage object or dict from Claude API

    Returns:
        Dict with input_tokens, output_tokens, and temporary cache token fields
    """
    if not usage:
        return {}

    get = (
        usage.get
        if isinstance(usage, dict)
        else lambda k: getattr(usage, k, None)
    )

    def to_int(value):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    meta: Dict[str, Any] = {}

    # Standard OpenTelemetry fields
    if (v := to_int(get("input_tokens"))) is not None:
        meta["input_tokens"] = v
    if (v := to_int(get("output_tokens"))) is not None:
        meta["output_tokens"] = v

    # Temporarily extract cache tokens for summing (will be summed by sum_anthropic_tokens)
    if (v := to_int(get("cache_read_input_tokens"))) is not None:
        meta["cache_read_input_tokens"] = v
    if (v := to_int(get("cache_creation_input_tokens"))) is not None:
        meta["cache_creation_input_tokens"] = v

    return meta


def sum_anthropic_tokens(usage_metadata: Dict[str, Any]) -> Dict[str, int]:
    """
    Sum Anthropic cache tokens into input_tokens.

    Anthropic returns cache tokens separately (cache_read_input_tokens, cache_creation_input_tokens).
    This function combines them into the standard input_tokens field for OpenTelemetry reporting.

    Args:
        usage_metadata: Usage metadata dict with input_tokens, output_tokens, and optional cache tokens

    Returns:
        Dict with only standard OpenTelemetry fields: input_tokens and output_tokens
    """
    # Get standard token counts
    input_tokens = usage_metadata.get("input_tokens") or 0
    output_tokens = usage_metadata.get("output_tokens") or 0

    # Get cache tokens (these are temporary fields, not in OpenTelemetry standard)
    cache_read = usage_metadata.get("cache_read_input_tokens") or 0
    cache_create = usage_metadata.get("cache_creation_input_tokens") or 0

    # Sum all input tokens (standard + cache)
    total_input_tokens = input_tokens + cache_read + cache_create

    # Return only standard OpenTelemetry fields
    return {
        "input_tokens": total_input_tokens,
        "output_tokens": output_tokens,
    }


def extract_usage_from_result_message(message: Any) -> Dict[str, Any]:
    """Normalize and merge token usage metrics from a `ResultMessage`."""
    if not getattr(message, "usage", None):
        return {}
    metrics = extract_usage_metadata(message.usage)
    return sum_anthropic_tokens(metrics) if metrics else {}
