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

"""Semantic conventions for LangChain instrumentation.

This module defines semantic conventions following OpenTelemetry GenAI
semantic conventions specification.
"""

from __future__ import annotations

from enum import Enum


class GenAISpanKindValues(str, Enum):
    """Values for gen_ai.operation.name attribute for LangChain operations.

    These extend the standard GenAI operation types with LangChain-specific
    operations for workflows, tasks, and agents.
    """

    CHAT = "chat"
    TEXT_COMPLETION = "text_completion"
    EMBEDDINGS = "embeddings"
    # LangChain-specific operation types
    WORKFLOW = "workflow"
    TASK = "task"
    TOOL = "execute_tool"
    AGENT = "agent"
    CHAIN = "chain"
    UNKNOWN = "unknown"


class LLMRequestTypeValues(str, Enum):
    """Values for the gen_ai.operation.name attribute."""

    CHAT = "chat"
    COMPLETION = "text_completion"
    EMBEDDING = "embeddings"
    RERANK = "rerank"
    UNKNOWN = "unknown"


# Custom span attributes for LangChain instrumentation
class SpanAttributes:
    """Span attributes for LangChain instrumentation.

    Follows OpenTelemetry GenAI semantic conventions where applicable.
    """

    # LangChain-specific attributes (following gen_ai.* namespace)
    LANGCHAIN_ENTITY_NAME = "gen_ai.langchain.entity.name"
    LANGCHAIN_ENTITY_PATH = "gen_ai.langchain.entity.path"
    LANGCHAIN_WORKFLOW_NAME = "gen_ai.langchain.workflow.name"

    # Association properties prefix (for metadata)
    LANGCHAIN_METADATA = "gen_ai.langchain.metadata"

    # LLM request functions (for tool/function calling)
    LLM_REQUEST_FUNCTIONS = "gen_ai.request.tools"

    # Token usage (additional attributes not in semconv yet)
    LLM_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
    LLM_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.input_tokens_details.cached"


# Meter names for metrics
class MeterNames:
    """Metric names for LangChain instrumentation."""

    LLM_OPERATION_DURATION = "gen_ai.client.operation.duration"
    LLM_TOKEN_USAGE = "gen_ai.client.token.usage"
