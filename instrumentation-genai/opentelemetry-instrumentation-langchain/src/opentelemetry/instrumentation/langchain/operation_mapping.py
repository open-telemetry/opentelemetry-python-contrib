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

"""Callback-to-semconv operation mapping for LangChain callbacks.

Maps each LangChain callback to the correct GenAI semantic convention
operation name.  Direct callbacks (``on_chat_model_start``,
``on_llm_start``, ``on_tool_start``, ``on_retriever_start``) have a
fixed 1-to-1 mapping.  ``on_chain_start`` requires heuristic
classification because LangChain emits this callback for agents,
workflows, and internal plumbing alike.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)

__all__ = [
    "OperationName",
    "classify_chain_run",
    "resolve_agent_name",
    "should_ignore_chain",
]

# ---------------------------------------------------------------------------
# Operation name constants (sourced from the GenAI semconv enum where
# available, with string fallbacks for values not yet in the enum).
# ---------------------------------------------------------------------------


class OperationName:
    """Canonical GenAI semantic convention operation names."""

    CHAT: str = GenAI.GenAiOperationNameValues.CHAT.value
    TEXT_COMPLETION: str = GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value
    INVOKE_AGENT: str = GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
    EXECUTE_TOOL: str = GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
    # invoke_workflow is not yet in the semconv enum; use the expected
    # string value so the mapping is forward-compatible.
    INVOKE_WORKFLOW: str = "invoke_workflow"


# ---------------------------------------------------------------------------
# LangGraph markers – names and prefixes produced by LangGraph that must
# be recognized when classifying ``on_chain_start`` callbacks.
# ---------------------------------------------------------------------------

LANGGRAPH_NODE_KEY = "langgraph_node"
LANGGRAPH_START_NODE = "__start__"
MIDDLEWARE_PREFIX = "Middleware."
LANGGRAPH_IDENTIFIER = "LangGraph"

# Metadata keys used by callers to override classification.
_META_AGENT_SPAN = "otel_agent_span"
_META_WORKFLOW_SPAN = "otel_workflow_span"
_META_AGENT_NAME = "agent_name"
_META_AGENT_TYPE = "agent_type"
_META_OTEL_TRACE = "otel_trace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_agent_name(
    serialized: dict[str, Any],
    metadata: Optional[dict[str, Any]],
    kwargs: dict[str, Any],
) -> Optional[str]:
    """Derive the best-effort agent name from callback arguments.

    Checks (in priority order):
    1. ``metadata["agent_name"]``
    2. ``kwargs["name"]``
    3. ``serialized["name"]``
    4. ``metadata["langgraph_node"]`` (if present and not a start node)
    """
    if metadata:
        name = metadata.get(_META_AGENT_NAME)
        if name:
            return str(name)

    name = kwargs.get("name")
    if name:
        return str(name)

    name = serialized.get("name")
    if name:
        return str(name)

    if metadata:
        node = metadata.get(LANGGRAPH_NODE_KEY)
        if node and node != LANGGRAPH_START_NODE:
            return str(node)

    return None


def _has_agent_signals(metadata: Optional[dict[str, Any]]) -> bool:
    """Return True when metadata contains any signal that the chain is an agent."""
    if not metadata:
        return False
    return bool(
        metadata.get(_META_AGENT_SPAN)
        or metadata.get(_META_AGENT_NAME)
        or metadata.get(_META_AGENT_TYPE)
    )


def _is_langgraph_agent_node(
    serialized: dict[str, Any],
    metadata: Optional[dict[str, Any]],
    kwargs: dict[str, Any],
) -> bool:
    """Detect a LangGraph agent node that is not a start/middleware node."""
    if not metadata:
        return False

    node = metadata.get(LANGGRAPH_NODE_KEY)
    if not node:
        return False

    # Exclude start and middleware nodes.
    if node == LANGGRAPH_START_NODE:
        return False

    name = resolve_agent_name(serialized, metadata, kwargs)
    if name and name.startswith(MIDDLEWARE_PREFIX):
        return False

    return True


def _looks_like_workflow(
    serialized: dict[str, Any],
    metadata: Optional[dict[str, Any]],
    parent_run_id: Optional[UUID],
) -> bool:
    """Return True if the chain looks like a top-level workflow/graph."""
    if parent_run_id is not None:
        return False

    # An explicit workflow override is authoritative.
    if metadata and metadata.get(_META_WORKFLOW_SPAN):
        return True

    # Heuristic: check for LangGraph identifier in the serialized repr.
    name = serialized.get("name", "")
    graph_id = (
        serialized.get("graph", {}).get("id", "")
        if isinstance(serialized.get("graph"), dict)
        else ""
    )
    return LANGGRAPH_IDENTIFIER in name or LANGGRAPH_IDENTIFIER in graph_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_ignore_chain(
    metadata: Optional[dict[str, Any]],
    agent_name: Optional[str],
    parent_run_id: Optional[UUID],
    kwargs: dict[str, Any],
) -> bool:
    """Return True if the chain callback should be silently suppressed.

    Suppression happens when:
    * The node is the LangGraph ``__start__`` node.
    * The name carries the ``Middleware.`` prefix.
    * ``metadata["otel_trace"]`` is explicitly ``False``.
    * ``metadata["otel_agent_span"]`` is explicitly ``False`` and no other
      agent signals are present.
    """
    if metadata:
        node = metadata.get(LANGGRAPH_NODE_KEY)
        if node == LANGGRAPH_START_NODE:
            return True

        if metadata.get(_META_OTEL_TRACE) is False:
            return True

        if (
            metadata.get(_META_AGENT_SPAN) is False
            and not metadata.get(_META_AGENT_NAME)
            and not metadata.get(_META_AGENT_TYPE)
        ):
            return True

    if agent_name and agent_name.startswith(MIDDLEWARE_PREFIX):
        return True

    name_from_kwargs = kwargs.get("name", "")
    if isinstance(name_from_kwargs, str) and name_from_kwargs.startswith(
        MIDDLEWARE_PREFIX
    ):
        return True

    return False


def classify_chain_run(
    serialized: dict[str, Any],
    metadata: Optional[dict[str, Any]],
    kwargs: dict[str, Any],
    parent_run_id: Optional[UUID] = None,
) -> Optional[str]:
    """Classify a ``on_chain_start`` callback into a semconv operation.

    Returns one of the :class:`OperationName` constants, or ``None`` when
    the chain should be suppressed (no span emitted).

    Classification order:
    1. Check for explicit suppression signals.
    2. Check for agent signals → ``invoke_agent``.
    3. Check for workflow signals → ``invoke_workflow``.
    4. Default: ``None`` (suppress – unclassified chains are not emitted).
    """
    agent_name = resolve_agent_name(serialized, metadata, kwargs)

    # 1. Suppress known noise.
    if should_ignore_chain(metadata, agent_name, parent_run_id, kwargs):
        return None

    # 2. Agent detection.
    if _has_agent_signals(metadata):
        return OperationName.INVOKE_AGENT

    if _is_langgraph_agent_node(serialized, metadata, kwargs):
        return OperationName.INVOKE_AGENT

    # 3. Workflow / orchestration detection.
    if _looks_like_workflow(serialized, metadata, parent_run_id):
        return OperationName.INVOKE_WORKFLOW

    # 4. Default: suppress unclassified chains.
    return None
